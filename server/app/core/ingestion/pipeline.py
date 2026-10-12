import asyncio
import hashlib
import time
from pathlib import Path

from loguru import logger

from app.core.domain import (
    ChunkDraft,
    DocumentStatus,
    EmbeddedChunk,
    IngestReport,
)
from app.core.interfaces import (
    Chunker,
    ChunkWriter,
    DocumentLoader,
    DocumentStore,
    Embedder,
)


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
        path = Path(path)
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        doc = await self.documents.get_or_create(user_id, path.stem)
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
        timings: dict[str, float] = {}
        try:
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
                user_id,
                [EmbeddedChunk(d, tuple(v)) for d, v in zip(drafts, vectors)],
            )
            await self.documents.mark_indexed(
                doc.id,
                title=parsed.title,
                num_pages=parsed.num_pages,
                num_chunks=n,
                content_hash=content_hash,
            )
            timings["store"] = _ms(t)
        except Exception as e:
            await self.documents.mark_failed(doc.id, f"{type(e).__name__}: {e}")
            raise
        return IngestReport(
            document_id=doc.id,
            title=parsed.title,
            num_pages=parsed.num_pages,
            num_chunks=n,
            timings_ms=timings,
        )
