import asyncio
import hashlib
import time
from dataclasses import replace
from pathlib import Path

from loguru import logger

from app.core.domain import (
    ChunkDraft,
    DocumentRecord,
    DocumentStatus,
    EmbeddedChunk,
    IngestReport,
)
from app.core.errors import DocumentLoadError
from app.core.interfaces import (
    Chunker,
    ChunkWriter,
    DocumentLoader,
    DocumentStore,
    Embedder,
)
from app.core.storage.naming import canonical_document_name


def embed_text(draft: ChunkDraft) -> str:
    """Text đưa vào embedding: thêm section làm contextual header."""
    if draft.section:
        return f"{draft.section}\n{draft.content}"
    return draft.content


def _ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


class IngestionPipeline:
    def __init__(
        self,
        loader: DocumentLoader,
        chunker: Chunker,
        embedder: Embedder,
        documents: DocumentStore,
        chunks: ChunkWriter,
    ):
        self.loader = loader
        self.chunker = chunker
        self.embedder = embedder
        self.documents = documents
        self.chunks = chunks

    async def ingest(
        self, path: Path, user_id: str, *, force: bool = False
    ) -> IngestReport:
        """CLI: hash → get_or_create → skip → mark_processing → run()."""
        path = Path(path)
        name = canonical_document_name(path.name)
        if name is None:
            raise DocumentLoadError(f"Tên file không hợp lệ: {path.name!r}")
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        doc = await self.documents.get_or_create(user_id, name)
        if (
            doc.status == DocumentStatus.INDEXED
            and doc.content_hash == content_hash
            and not force
        ):
            logger.info("Skip {} (đã index, hash không đổi)", path.name)
            return IngestReport(
                document_id=doc.id,
                skipped=True,
                title=doc.title,
                num_chunks=doc.num_chunks,
            )

        await self.documents.mark_processing(doc.id)
        try:
            return await self.run(replace(doc, content_hash=content_hash), path)
        except Exception as e:
            await self.documents.mark_failed(doc.id, f"{type(e).__name__}: {e}")
            raise

    async def run(self, doc: DocumentRecord, path: Path) -> IngestReport:
        """load → chunk → embed → replace_document_chunks → mark_indexed.
        KHÔNG gọi mark_processing / mark_failed (caller lo phần đó)."""
        timings: dict[str, float] = {}
        t = time.perf_counter()
        parsed = await asyncio.to_thread(self.loader.load, path)
        timings["load"] = _ms(t)

        t = time.perf_counter()
        drafts = await asyncio.to_thread(self.chunker.chunk, parsed)
        timings["chunk"] = _ms(t)

        t = time.perf_counter()
        vectors = await self.embedder.embed_documents(
            parsed.title, [embed_text(d) for d in drafts]
        )
        timings["embed"] = _ms(t)

        t = time.perf_counter()
        n = await self.chunks.replace_document_chunks(
            doc.id,
            doc.user_id,
            [EmbeddedChunk(d, tuple(v)) for d, v in zip(drafts, vectors)],
        )
        await self.documents.mark_indexed(
            doc.id,
            title=parsed.title,
            num_pages=parsed.num_pages,
            num_chunks=n,
            content_hash=doc.content_hash,
        )
        timings["store"] = _ms(t)
        return IngestReport(
            document_id=doc.id,
            title=parsed.title,
            num_pages=parsed.num_pages,
            num_chunks=n,
            timings_ms=timings,
        )
