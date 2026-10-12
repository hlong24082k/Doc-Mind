"""Các Protocol mà pipeline phụ thuộc vào (DIP)."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Protocol, Sequence

from app.core.domain import (
    ChunkDraft,
    DocumentRecord,
    EmbeddedChunk,
    ParsedDocument,
    RetrievedChunk,
    ScoredChunk,
    SearchScope,
)


class DocumentLoader(Protocol):
    def load(self, path: Path) -> ParsedDocument: ...


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


class Chunker(Protocol):
    def chunk(self, document: ParsedDocument) -> list[ChunkDraft]: ...


class Embedder(Protocol):
    @property
    def dimension(self) -> int: ...

    async def embed_documents(
        self, title: str, texts: Sequence[str]
    ) -> list[list[float]]: ...

    async def embed_query(self, query: str) -> list[float]: ...


class DocumentStore(Protocol):
    async def get_or_create(self, user_id: str, name: str) -> DocumentRecord: ...

    async def get(self, document_id: str) -> DocumentRecord | None: ...

    async def list_for_user(self, user_id: str) -> list[DocumentRecord]: ...

    async def mark_processing(self, document_id: str) -> None: ...

    async def mark_indexed(
        self,
        document_id: str,
        *,
        title: str,
        num_pages: int,
        num_chunks: int,
        content_hash: str,
    ) -> None: ...

    async def mark_failed(self, document_id: str, error: str) -> None: ...


class ChunkWriter(Protocol):
    async def replace_document_chunks(
        self,
        document_id: str,
        user_id: str,
        chunks: Sequence[EmbeddedChunk],
    ) -> int: ...


class ChunkReader(Protocol):
    async def get_window(
        self, document_id: str, first_index: int, last_index: int
    ) -> list[RetrievedChunk]: ...

    async def sample(self, scope: SearchScope, n: int) -> list[RetrievedChunk]: ...


class Retriever(Protocol):
    async def retrieve(
        self,
        query: str,
        scope: SearchScope,
        k: int,
        timings: dict[str, float] | None = None,  # retriever ghi timing con vào đây
    ) -> list[ScoredChunk]: ...


class FusionStrategy(Protocol):
    def fuse(
        self, ranked: Mapping[str, Sequence[ScoredChunk]], k: int
    ) -> list[ScoredChunk]: ...


class Reranker(Protocol):
    async def rerank(
        self,
        query: str,
        candidates: Sequence[ScoredChunk],
        top_n: int,
    ) -> list[ScoredChunk]: ...
