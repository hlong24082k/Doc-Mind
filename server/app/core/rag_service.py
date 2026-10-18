import time
from typing import AsyncIterator

from app.core.domain import (
    Answer,
    ContextBlock,
    ContextsEvent,
    FinalEvent,
    SearchResult,
    SearchScope,
    TokenEvent,
)
from app.core.generation.answer_generator import AnswerGenerator
from app.core.generation.citations import (
    build_citations,
    is_grounded,
    is_refusal,
)
from app.core.generation.context_builder import ContextBuilder
from app.core.interfaces import Retriever
from app.core.prompt.rag_prompts import REFUSAL_TEXT


def _ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


class RAGService:
    """Orchestrator truy vấn: retrieve → context → generate."""

    def __init__(
        self,
        retriever: Retriever,
        context_builder: ContextBuilder,
        generator: AnswerGenerator,
        candidates: int = 30,
        top_n: int = 5,
        min_dense_score: float | None = None,
    ):
        self.retriever = retriever
        self.context_builder = context_builder
        self.generator = generator
        self.candidates = candidates
        self.top_n = top_n
        self.min_dense_score = min_dense_score

    async def search(
        self,
        query: str,
        scope: SearchScope,
        *,
        k: int | None = None,
    ) -> SearchResult:
        timings: dict[str, float] = {}
        total = time.perf_counter()

        t = time.perf_counter()
        found = await self.retriever.retrieve(
            query, scope, max(self.candidates, k or 0), timings
        )
        timings["retrieve"] = _ms(t)

        # Chặn sớm câu hỏi ngoài lề: không chunk nào đủ gần về ngữ nghĩa thì
        # bỏ qua LLM. Retriever sparse-only không có điểm dense → không chặn.
        dense = [c.scores["dense"] for c in found if "dense" in c.scores]
        if self.min_dense_score is not None and dense:
            if max(dense) < self.min_dense_score:
                found = []

        chunks = found[: k or self.top_n]

        timings["total"] = _ms(total)
        return SearchResult(chunks=tuple(chunks), timings_ms=timings)

    async def _prepare(
        self, query: str, scope: SearchScope
    ) -> tuple[SearchResult, list[ContextBlock], dict[str, float]]:
        result = await self.search(query, scope)
        timings = dict(result.timings_ms)
        # "total" của search chỉ là thời gian tìm kiếm; total của answer
        # được ghi lại ở cuối (end-to-end)
        timings.pop("total", None)
        contexts: list[ContextBlock] = []
        if result.chunks:
            t = time.perf_counter()
            contexts = await self.context_builder.build(result.chunks)
            timings["context"] = _ms(t)
        return result, contexts, timings

    def _refusal(self, query: str, timings: dict[str, float], start: float) -> Answer:
        timings["total"] = _ms(start)
        return Answer(
            query=query,
            text=REFUSAL_TEXT,
            citations=(),
            contexts=(),
            grounded=True,
            refused=True,
            timings_ms=timings,
        )

    def _finalize(
        self,
        query: str,
        text: str,
        contexts: list[ContextBlock],
        timings: dict[str, float],
        start: float,
    ) -> Answer:
        citations, invalid = build_citations(text, contexts)
        timings["total"] = _ms(start)
        return Answer(
            query=query,
            text=text,
            citations=tuple(citations),
            contexts=tuple(contexts),
            grounded=is_grounded(text, citations, invalid),
            refused=is_refusal(text),
            timings_ms=timings,
        )

    async def answer(self, query: str, scope: SearchScope) -> Answer:
        start = time.perf_counter()
        result, contexts, timings = await self._prepare(query, scope)
        if not result.chunks:
            return self._refusal(query, timings, start)

        t = time.perf_counter()
        text, _ = await self.generator.generate(query, contexts)
        timings["llm"] = _ms(t)
        return self._finalize(query, text, contexts, timings, start)

    async def answer_stream(
        self, query: str, scope: SearchScope
    ) -> AsyncIterator[ContextsEvent | TokenEvent | FinalEvent]:
        start = time.perf_counter()
        result, contexts, timings = await self._prepare(query, scope)
        if not result.chunks:
            yield ContextsEvent(contexts=())
            yield TokenEvent(text=REFUSAL_TEXT)
            yield FinalEvent(answer=self._refusal(query, timings, start))
            return

        yield ContextsEvent(contexts=tuple(contexts))
        parts: list[str] = []
        t = time.perf_counter()
        async for token in self.generator.stream(query, contexts):
            parts.append(token)
            yield TokenEvent(text=token)
        timings["llm"] = _ms(t)
        text = "".join(parts).strip()
        yield FinalEvent(answer=self._finalize(query, text, contexts, timings, start))
