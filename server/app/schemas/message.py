# src/app/schemas/message.py

from pydantic import BaseModel

from app.models.message import MessageSenderType


class MessageBase(BaseModel):
    content: str
    sender_type: MessageSenderType


class MessageCreate(MessageBase):
    pass
