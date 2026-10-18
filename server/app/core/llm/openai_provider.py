from typing import Any, AsyncIterator

from openai import AsyncOpenAI
from sse_starlette.event import ServerSentEvent

from app.core.errors import LLMGenerationError
from app.core.llm.base import LLMBase, LLMResponse


class OpenAIProvider(LLMBase):
    """Chat Completions qua OpenAI SDK: chạy với mọi endpoint tương thích
    OpenAI (OpenAI, Gemini OpenAI-compat, vLLM serve, OpenRouter...)."""

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        *,
        reasoning_effort: str | None = None,
    ):
        super().__init__(provider_name="openai")
        self.client = client
        self.model = model
        self.reasoning_effort = reasoning_effort

    def _request(
        self, query: str, system_instruction: str | None
    ) -> dict[str, Any]:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": query})
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        # nhiều model trên vLLM không nhận tham số này → chỉ gửi khi có cấu hình
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        return kwargs

    async def _generate_stream(
        self, query: str, system_instruction: str | None
    ) -> AsyncIterator[ServerSentEvent]:
        try:
            stream = await self.client.chat.completions.create(
                **self._request(query, system_instruction), stream=True
            )
            # async with: client ngắt kết nối → CancelledError → đóng HTTP
            # response, upstream ngừng sinh token (không tốn thêm quota)
            async with stream:
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield ServerSentEvent(
                            data=chunk.choices[0].delta.content, event="message"
                        )
        except Exception as e:  # CancelledError là BaseException → propagate
            yield ServerSentEvent(
                data=f"[Error] LLM streaming failed: {e}", event="error"
            )

    async def _generate_once(
        self, query: str, system_instruction: str | None
    ) -> LLMResponse:
        try:
            resp = await self.client.chat.completions.create(
                **self._request(query, system_instruction)
            )
        except Exception as e:
            raise LLMGenerationError(f"LLM generation failed: {e}") from e
        choice = resp.choices[0] if resp.choices else None
        return LLMResponse(
            text=choice.message.content if choice else None,
            provider=self.provider,
            metadata={
                "model": self.model,
                "finish_reason": choice.finish_reason if choice else None,
                "usage": resp.usage.model_dump() if resp.usage else None,
            },
        )
