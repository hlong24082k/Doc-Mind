import asyncio
from typing import AsyncIterator

from google import genai
from google.genai import types
from sse_starlette.event import ServerSentEvent

from app.config import settings
from app.core.errors import LLMGenerationError
from app.core.llm.base import LLMBase, LLMResponse


class GeminiProvider(LLMBase):
    """
    Gemini LLM provider implementation.
    """

    def __init__(
        self,
        model_name: str | None = None,
        *,
        api_key: str | None = None,
        thinking_level: str | None = None,
        client: genai.Client | None = None,
    ):
        """
        :param model_name: Gemini model name, mặc định settings.gemini_model
        :param api_key: Google API key, mặc định settings.gemini_api_key
        :param thinking_level: minimal | low | medium | high
        :param client: client dùng chung (factory truyền vào)
        """
        super().__init__(provider_name="gemini")
        self.model_name = model_name or settings.gemini_model
        self.thinking_level = thinking_level or settings.gemini_thinking_level
        self.client = client or genai.Client(api_key=api_key or settings.gemini_api_key)

        self.safety_settings = [
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
        ]

    @staticmethod
    def _build_contents(query: str) -> list[types.Content]:
        return [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=query)],
            ),
        ]

    def _build_config(
        self, system_instruction: str | None
    ) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(
                thinking_level=self.thinking_level,
            ),
            safety_settings=self.safety_settings,
            system_instruction=system_instruction,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        )

    async def _generate_stream(
        self, query: str, system_instruction: str | None
    ) -> AsyncIterator[ServerSentEvent]:
        # SDK async: không tốn OS thread mỗi request, và hủy được (client
        # ngắt kết nối → CancelledError hủy luôn request HTTP tới Gemini)
        try:
            stream = await self.client.aio.models.generate_content_stream(
                model=self.model_name,
                contents=self._build_contents(query),
                config=self._build_config(system_instruction),
            )
            async for chunk in stream:
                if chunk.text:
                    yield ServerSentEvent(data=chunk.text, event="message")
        except Exception as e:  # CancelledError là BaseException → propagate
            yield ServerSentEvent(
                data=f"[Error] Gemini streaming failed: {e}", event="error"
            )

    async def _generate_once(
        self, query: str, system_instruction: str | None
    ) -> LLMResponse:
        try:
            resp = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=self._build_contents(query),
                config=self._build_config(system_instruction),
            )
        except Exception as e:
            raise LLMGenerationError(f"Gemini generation failed: {e}") from e

        finish_reason = None
        if resp.candidates:
            finish_reason = resp.candidates[0].finish_reason
        return LLMResponse(
            text=resp.text,
            provider=self.provider,
            metadata={
                "model": self.model_name,
                "finish_reason": (
                    str(finish_reason) if finish_reason is not None else None
                ),
                "usage": (
                    resp.usage_metadata.model_dump() if resp.usage_metadata else None
                ),
            },
        )


if __name__ == "__main__":

    async def main():
        gemini = GeminiProvider()
        query = "Explain the theory of relativity in simple terms."

        print("Gemini Response (stream):")
        async for chunk in gemini.generate(query):
            print(chunk.data, end="", flush=True)

        print("\n\nGemini Response (non-stream):")
        resp = await gemini.generate(query, stream=False)
        print(resp.text)
        print(resp.metadata)

    asyncio.run(main())
