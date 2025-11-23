# src/app/routers/conversation/endpoint.py

from fastapi import APIRouter, status, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.app.db.session import get_db
from src.app.schemas import message as schema_message
from src.app.routers.conversation.services import ChatStreamService


conversation_router = APIRouter()


@conversation_router.post(
    "/stream",
    status_code=status.HTTP_200_OK,
)
async def stream_conversation(
    message_in: schema_message.MessageCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    chat_stream_service = ChatStreamService(db)
    return await chat_stream_service.stream_conversation(message_in.content)
