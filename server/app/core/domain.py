"""Domain thuần: chỉ dataclass, không phụ thuộc SQLAlchemy hay Gemini."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from typing import Mapping


class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class TextBlock:
    page_number: int
    text: str
    is_heading: bool


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    title: str
    num_pages: int
    blocks: tuple[TextBlock, ...]


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    chunk_index: int
    content: str
    section: str | None
    page_start: int
    page_end: int
    token_count: int
    overlap_chars: int


@dataclass(frozen=True, slots=True)
class EmbeddedChunk:
    draft: ChunkDraft
    embedding: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    id: str
    user_id: str
    name: str
    title: str | None
    status: DocumentStatus
    content_hash: str | None
    num_chunks: int
    indexed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SearchScope:
    user_id: str
    document_ids: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: int
    document_id: str
    document_name: str
    document_title: str | None
    chunk_index: int
    content: str
    section: str | None
    page_start: int
    page_end: int
    overlap_chars: int


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    chunk: RetrievedChunk
    score: float
    # {"dense": .., "sparse": .., "rrf": .., "rerank": ..}
    scores: Mapping[str, float] = field(default_factory=dict)
    # {"dense": 3, "sparse": 1}
    ranks: Mapping[str, int] = field(default_factory=dict)

    def with_score(
        self, name: str, value: float, *, primary: bool = True
    ) -> "ScoredChunk":
        """Bản sao có thêm điểm `name`, giữ toàn bộ lịch sử điểm."""
        scores = {**self.scores, name: value}
        return replace(self, score=value if primary else self.score, scores=scores)


@dataclass(frozen=True, slots=True)
class ContextBlock:
    ref: int
    document_id: str
    document_name: str
    page_start: int
    page_end: int
    section: str | None
    text: str
    chunk_ids: tuple[int, ...]
    document_title: str | None = None


@dataclass(frozen=True, slots=True)
class Citation:
    ref: int
    document_id: str
    document_name: str
    page_start: int
    page_end: int


@dataclass(frozen=True, slots=True)
class Answer:
    query: str
    text: str
    citations: tuple[Citation, ...]
    contexts: tuple[ContextBlock, ...]
    grounded: bool
    refused: bool
    timings_ms: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class SearchResult:
    chunks: tuple[ScoredChunk, ...]
    timings_ms: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class IngestReport:
    document_id: str
    skipped: bool = False
    title: str | None = None
    num_pages: int = 0
    num_chunks: int = 0
    timings_ms: Mapping[str, float] = field(default_factory=dict)


# Event cho answer streaming (thuộc core, không phải SSE)
@dataclass(frozen=True, slots=True)
class ContextsEvent:
    contexts: tuple[ContextBlock, ...]


@dataclass(frozen=True, slots=True)
class TokenEvent:
    text: str


@dataclass(frozen=True, slots=True)
class FinalEvent:
    answer: Answer
