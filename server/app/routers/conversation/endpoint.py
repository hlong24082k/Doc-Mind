# src/app/routers/conversation/endpoint.py

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.routers.conversation.services import ChatStreamService
from app.schemas import message as schema_message

conversation_router = APIRouter()


@conversation_router.post(
    "/stream",
    status_code=status.HTTP_200_OK,
)
async def stream_conversation(
    message_in: schema_message.MessageCreate,
    db: AsyncSession = Depends(get_db),
):
    chat_stream_service = ChatStreamService(db)
    return await chat_stream_service.stream_conversation(message_in.content)
