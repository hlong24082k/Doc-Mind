from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.domain import DocumentRecord, DocumentStatus
from app.models.document import Document


def _to_record(d: Document) -> DocumentRecord:
    return DocumentRecord(
        id=d.id,
        user_id=d.user_id,
        name=d.name,
        title=d.title,
        status=DocumentStatus(d.status),
        content_hash=d.content_hash,
        num_chunks=d.num_chunks,
        indexed_at=d.indexed_at,
    )


class PgDocumentRepository:
    """DocumentStore trên PostgreSQL."""

    def __init__(self, session_factory: async_sessionmaker):
        self._sf = session_factory

    async def get_or_create(self, user_id: str, name: str) -> DocumentRecord:
        async with self._sf() as session:
            doc = (
                (
                    await session.execute(
                        select(Document).where(
                            Document.user_id == user_id, Document.name == name
                        )
                    )
                )
                .scalars()
                .first()
            )
            if doc is None:
                doc = Document(user_id=user_id, name=name, status="pending")
                session.add(doc)
                await session.commit()
                await session.refresh(doc)
            return _to_record(doc)

    async def get(self, document_id: str) -> DocumentRecord | None:
        async with self._sf() as session:
            doc = await session.get(Document, document_id)
            return _to_record(doc) if doc else None

    async def list_for_user(self, user_id: str) -> list[DocumentRecord]:
        async with self._sf() as session:
            rows = (
                await session.execute(
                    select(Document)
                    .where(Document.user_id == user_id)
                    .order_by(Document.created_at)
                )
            ).scalars()
            return [_to_record(d) for d in rows]

    async def _update(self, document_id: str, **values) -> None:
        async with self._sf() as session:
            await session.execute(
                update(Document).where(Document.id == document_id).values(**values)
            )
            await session.commit()

    async def mark_processing(self, document_id: str) -> None:
        await self._update(document_id, status="processing", error=None)

    async def mark_indexed(
        self,
        document_id: str,
        *,
        title: str,
        num_pages: int,
        num_chunks: int,
        content_hash: str,
    ) -> None:
        await self._update(
            document_id,
            status="indexed",
            title=title[:512],
            num_pages=num_pages,
            num_chunks=num_chunks,
            content_hash=content_hash,
            error=None,
            indexed_at=datetime.utcnow(),
        )

    async def mark_failed(self, document_id: str, error: str) -> None:
        await self._update(
            document_id,
            status="failed",
            error=error,
            indexed_at=datetime.utcnow(),
        )
