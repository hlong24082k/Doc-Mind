from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_serializer

RejectReason = Literal[
    "not_pdf", "too_large", "empty_name", "busy", "unchanged", "quota_exceeded"
]


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    title: str | None
    status: str
    error: str | None
    size_bytes: int
    num_pages: int | None
    num_chunks: int
    created_at: datetime
    indexed_at: datetime | None

    @model_serializer(mode="wrap")
    def _with_legacy_id(self, handler):
        # giữ `_id` để tương thích ngược với client cũ
        return {"_id": self.id, **handler(self)}


class Usage(BaseModel):
    bytes: int
    documents: int
    quota_bytes: int
    quota_documents: int


class RejectedFile(BaseModel):
    filename: str
    reason: RejectReason


class DocumentList(BaseModel):
    documents: list[DocumentOut]
    usage: Usage


class UploadResult(DocumentList):
    rejected: list[RejectedFile]
