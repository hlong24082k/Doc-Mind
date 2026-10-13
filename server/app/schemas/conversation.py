from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from app.config import settings


class ConversationCreate(BaseModel):
    document_ids: list[str] = Field(
        min_length=1, max_length=settings.conversation_max_documents
    )
    title: str | None = Field(None, max_length=255)

    @field_validator("document_ids")
    @classmethod
    def _unique(cls, ids: list[str]) -> list[str]:
        return list(dict.fromkeys(ids))


class DocumentRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    title: str | None
    status: str


class ConversationOut(BaseModel):
    id: str
    title: str | None
    documents: list[DocumentRef]
    created_at: datetime
    updated_at: datetime


class Source(BaseModel):
    ref: int
    document_id: str
    document_name: str
    document_title: str | None
    page_start: int
    page_end: int
    section: str | None
    snippet: str
    cited: bool


class MessageCreate(BaseModel):
    content: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=settings.chat_message_max_chars,
        ),
    ]


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: Literal["user", "assistant"]
    content: str
    sources: list[Source] | None
    grounded: bool | None
    refused: bool | None
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]
