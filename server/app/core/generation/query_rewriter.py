import asyncio
import re
from typing import Sequence

from loguru import logger

from app.core.llm.base import LLMBase

REWRITE_SYSTEM_PROMPT = """Rewrite the user's follow-up question into a standalone question \
that can be understood without the conversation. Keep the original language and keep \
technical terms verbatim. If it is already standalone, return it unchanged. \
Output only the question."""

_CITATION = re.compile(r"\s*\[\d+\]")
_PREFIX = re.compile(r"^(standalone\s+)?question\s*:\s*", re.IGNORECASE)
_QUOTES = "\"'`“”‘’"


def _clean(text: str) -> str:
    text = text.strip().strip(_QUOTES).strip()
    text = _PREFIX.sub("", text)
    return text.strip().strip(_QUOTES).strip()


class QueryRewriter:
    """Viết lại câu follow-up thành câu độc lập trước khi retrieve."""

    def __init__(self, llm: LLMBase, timeout_s: float = 8.0, max_chars: int = 500):
        self.llm = llm
        self.timeout_s = timeout_s
        self.max_chars = max_chars

    async def rewrite(self, question: str, history: Sequence[tuple[str, str]]) -> str:
        """history = [(role, content)…] theo thứ tự thời gian.
        Lỗi / timeout / kết quả rỗng / quá dài → trả câu gốc."""
        if not history:
            return question
        lines = [
            f"{role}: {_CITATION.sub('', content) if role == 'assistant' else content}"
            for role, content in history
        ]
        prompt = (
            "Conversation:\n" + "\n".join(lines) + f"\n\nFollow-up question: {question}"
        )
        try:
            resp = await asyncio.wait_for(
                self.llm.generate(
                    prompt,
                    system_instruction=REWRITE_SYSTEM_PROMPT,
                    stream=False,
                ),
                self.timeout_s,
            )
        except Exception as e:  # gồm cả TimeoutError
            logger.warning("Query rewrite failed: {}: {}", type(e).__name__, e)
            return question
        text = _clean(resp.text or "")
        if not text or len(text) > self.max_chars:
            logger.warning("Query rewrite unusable: {!r}", text[:100])
            return question
        return text
