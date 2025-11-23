# src/app/routers/conversation/services.py

from motor.motor_asyncio import AsyncIOMotorDatabase
from sse_starlette.sse import EventSourceResponse

from src.app.core.llm.base import LLMBase
from src.app.core.llm.gemini_provider import GeminiProvider

class ChatStreamService:
    def __init__(
        self, 
        db: AsyncIOMotorDatabase,
        ai_provider: LLMBase = GeminiProvider()
    ):
        self.db = db
        self.ai_provider = ai_provider

    async def __stream(self, message_content: str):
        response_chunks = []
        try:
            async for chunk in self.ai_provider.generate(message_content):
                if chunk.event == "message":
                    response_chunks.append(chunk.data)
                yield chunk
        except Exception as e:
            raise e
        finally:
            pass

    async def stream_conversation(self, message_content: str):
        return EventSourceResponse(
            self.__stream(message_content),
            media_type="text/event-stream"
        )
