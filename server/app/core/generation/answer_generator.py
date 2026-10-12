from typing import AsyncIterator, Sequence

from app.core.domain import ContextBlock
from app.core.errors import LLMGenerationError
from app.core.llm.base import LLMBase
from app.core.prompt.rag_prompts import RAG_SYSTEM_PROMPT, build_rag_user_prompt


class AnswerGenerator:
    def __init__(self, llm: LLMBase):
        self.llm = llm

    async def generate(
        self, question: str, contexts: Sequence[ContextBlock]
    ) -> tuple[str, dict]:
        resp = await self.llm.generate(
            build_rag_user_prompt(question, contexts),
            system_instruction=RAG_SYSTEM_PROMPT,
            stream=False,
        )
        return (resp.text or "").strip(), resp.metadata or {}

    async def stream(
        self, question: str, contexts: Sequence[ContextBlock]
    ) -> AsyncIterator[str]:
        async for event in self.llm.generate(
            build_rag_user_prompt(question, contexts),
            system_instruction=RAG_SYSTEM_PROMPT,
            stream=True,
        ):
            if event.event == "message":
                yield event.data
            elif event.event == "error":
                raise LLMGenerationError(event.data)
