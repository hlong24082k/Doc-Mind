import asyncio
import threading
import time
from typing import Any, Mapping, Sequence

from loguru import logger

from app.core.domain import ScoredChunk
from app.core.errors import RerankerUnavailableError

DEFAULT_QUESTION: Mapping[str, Any] = {
    "relevant": {
        "type": "noul",
        "instructions": (
            "Does the passage contain information that answers the question?"
        ),
    }
}


class LayaReranker:
    """Rerank bằng Laya typed-decisions (MLX): P(passage trả lời câu hỏi)."""

    def __init__(
        self,
        model_id: str,
        dtype: str = "float16",
        batch_size: int = 16,
        question: Mapping[str, Any] = DEFAULT_QUESTION,
    ):
        self.model_id = model_id
        self.dtype = dtype
        self.batch_size = batch_size
        self.question = dict(question)
        self._agent = None
        self._lock = threading.Lock()

    def _load(self):
        if self._agent is not None:
            return self._agent
        try:
            import laya_mlx as laya
        except ImportError as e:
            raise RerankerUnavailableError(
                "laya-mlx chỉ chạy trên Apple Silicon; đặt RERANKER=none"
            ) from e
        logger.info("Loading Laya model {}", self.model_id)
        self._agent = laya.load(
            self.model_id,
            dtype=self.dtype,
            batch_size=self.batch_size,
            cache_prompts=True,
        )
        return self._agent

    def _score_all(self, query: str, candidates: Sequence[ScoredChunk]) -> list[float]:
        with self._lock:
            agent = self._load()
            scores: list[float] = []
            start = time.perf_counter()
            for c in candidates:
                chunk = c.chunk
                passage = (
                    f"{chunk.section}\n{chunk.content}"
                    if chunk.section
                    else chunk.content
                )
                state = {"question": query, "passage": passage}
                result = agent.predict(state, self.question)
                scores.append(float(result["answers"]["relevant"]["noul"]))
                if result.get("usage", {}).get("truncated"):
                    logger.warning(
                        "Laya: passage của chunk {} bị cắt "
                        "(cân nhắc giảm chunk_max_tokens)",
                        chunk.chunk_id,
                    )
            total = (time.perf_counter() - start) * 1000
            if candidates:
                logger.info(
                    "Laya rerank {} candidates: {:.0f} ms ({:.1f} ms/cand)",
                    len(candidates),
                    total,
                    total / len(candidates),
                )
            return scores

    async def rerank(
        self,
        query: str,
        candidates: Sequence[ScoredChunk],
        top_n: int,
    ) -> list[ScoredChunk]:
        if not candidates:
            return []
        scores = await asyncio.to_thread(self._score_all, query, candidates)
        scored = [c.with_score("rerank", p) for c, p in zip(candidates, scores)]
        scored.sort(
            key=lambda s: (
                -s.scores["rerank"],
                -s.scores.get("rrf", 0.0),
                s.chunk.chunk_id,
            )
        )
        return scored[:top_n]
