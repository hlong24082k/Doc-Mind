import os

import asyncio
import threading

from collections import deque
from google import genai
from google.genai import types

from typing import Optional, List
from dotenv import load_dotenv

from src.llm.base import LLMBase, LLMResponse


load_dotenv(".env", override=True)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


class GeminiProvider(LLMBase):
    """
    Gemini LLM provider implementation.
    """

    def __init__(self, model_name: str = "gemini-1.5-flash"):
        """
        :param api_key: Google Generative AI API key
        :param model_name: Gemini model name (e.g. "gemini-1.5-pro" or "gemini-1.5-flash")
        """
        super().__init__(provider_name="gemini")
        self.model_name = model_name
        self.client = genai.Client(api_key=GEMINI_API_KEY)

        self.safety_settings = [
            types.SafetySetting(
                category= types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE, # BLOCK_LOW_AND_ABOVE
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

    def __run_gemini_stream_in_thread(self, query: str, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        """
        Internal method to run Gemini streaming in a separate thread.
        """
        try:
            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=query),
                    ],
                ),
            ]

            generate_content_config = types.GenerateContentConfig(
                thinking_config = types.ThinkingConfig(
                    thinking_budget=0,
                ),
                safety_settings=self.safety_settings,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                ),
            )

            response_stream = self.client.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                config=generate_content_config,
            )

            for chunk in response_stream:
                if chunk.text:
                    loop.call_soon_threadsafe(queue.put_nowait, chunk.text)

        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, f"[Error] Gemini streaming failed: {e}")

        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    async def generate(self, query: str):
        """
        Generate text using Gemini model.
        """
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()

        threading.Thread(
            target=self.__run_gemini_stream_in_thread,
            args=(query, queue, loop),
            daemon=True
        ).start()

        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk


if __name__ == "__main__":
    import asyncio

    async def main():
        gemini = GeminiProvider(model_name="gemini-2.5-flash")
        query = "Explain the theory of relativity in simple terms."

        print("Gemini Response:")
        async for chunk in gemini.generate(query):
            print(chunk, end="", flush=True)

    asyncio.run(main())
