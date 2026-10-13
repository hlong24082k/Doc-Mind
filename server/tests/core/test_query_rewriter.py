import asyncio

from app.core.generation.query_rewriter import QueryRewriter
from app.core.llm.base import LLMResponse

HISTORY = [
    ("user", "What is multi-head attention?"),
    ("assistant", "It runs several attention heads in parallel [1][2]."),
]


class FakeLLM:
    def __init__(self, text="", error=None, delay=0.0):
        self.text = text
        self.error = error
        self.delay = delay
        self.prompts: list[str] = []

    async def generate(self, query, *, system_instruction=None, stream=True):
        self.prompts.append(query)
        await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return LLMResponse(text=self.text)


async def test_empty_history_skips_llm():
    llm = FakeLLM("x")
    assert await QueryRewriter(llm).rewrite("q?", []) == "q?"
    assert llm.prompts == []


async def test_error_or_timeout_returns_original():
    boom = QueryRewriter(FakeLLM(error=RuntimeError("429")))
    assert await boom.rewrite("q?", HISTORY) == "q?"
    slow = QueryRewriter(FakeLLM("x", delay=1), timeout_s=0.01)
    assert await slow.rewrite("q?", HISTORY) == "q?"


async def test_strips_citations_and_prefix():
    llm = FakeLLM('Question: "What is the complexity of multi-head attention?"')
    out = await QueryRewriter(llm).rewrite("what about its complexity?", HISTORY)
    assert out == "What is the complexity of multi-head attention?"
    assert "[1]" not in llm.prompts[0]
    assert "what about its complexity?" in llm.prompts[0]


async def test_empty_or_too_long_returns_original():
    assert await QueryRewriter(FakeLLM("  ")).rewrite("q?", HISTORY) == "q?"
    long = QueryRewriter(FakeLLM("x" * 600), max_chars=500)
    assert await long.rewrite("q?", HISTORY) == "q?"
