from typing import Sequence

from sqlalchemy import bindparam, delete, insert, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.domain import EmbeddedChunk, RetrievedChunk, SearchScope
from app.models.document_chunk import DocumentChunk

CHUNK_COLUMNS = """
    c.id, c.document_id, d.name AS document_name, d.title AS document_title,
    c.chunk_index, c.content, c.section, c.page_start, c.page_end,
    c.overlap_chars
"""


def row_to_chunk(row) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=row.id,
        document_id=row.document_id,
        document_name=row.document_name,
        document_title=row.document_title,
        chunk_index=row.chunk_index,
        content=row.content,
        section=row.section,
        page_start=row.page_start,
        page_end=row.page_end,
        overlap_chars=row.overlap_chars,
    )


class PgChunkRepository:
    """ChunkWriter + ChunkReader trên PostgreSQL."""

    def __init__(self, session_factory: async_sessionmaker):
        self._sf = session_factory

    async def replace_document_chunks(
        self,
        document_id: str,
        user_id: str,
        chunks: Sequence[EmbeddedChunk],
    ) -> int:
        rows = [
            {
                "document_id": document_id,
                "user_id": user_id,
                "chunk_index": c.draft.chunk_index,
                "section": c.draft.section,
                "content": c.draft.content,
                "overlap_chars": c.draft.overlap_chars,
                "page_start": c.draft.page_start,
                "page_end": c.draft.page_end,
                "token_count": c.draft.token_count,
                "embedding": list(c.embedding),
            }
            for c in chunks
        ]
        async with self._sf() as session:
            async with session.begin():
                await session.execute(
                    delete(DocumentChunk).where(
                        DocumentChunk.document_id == document_id
                    )
                )
                if rows:
                    await session.execute(insert(DocumentChunk), rows)
        return len(rows)

    async def get_window(
        self, document_id: str, first_index: int, last_index: int
    ) -> list[RetrievedChunk]:
        stmt = text(f"""
            SELECT {CHUNK_COLUMNS}
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.document_id = :document_id
              AND c.chunk_index BETWEEN :first AND :last
            ORDER BY c.chunk_index
            """)
        async with self._sf() as session:
            result = await session.execute(
                stmt,
                {
                    "document_id": document_id,
                    "first": first_index,
                    "last": last_index,
                },
            )
            return [row_to_chunk(r) for r in result]

    async def sample(self, scope: SearchScope, n: int) -> list[RetrievedChunk]:
        doc_filter = "AND c.document_id IN :document_ids" if scope.document_ids else ""
        stmt = text(f"""
            SELECT {CHUNK_COLUMNS}
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.user_id = :user_id {doc_filter}
            ORDER BY random()
            LIMIT :n
            """)
        params: dict = {"user_id": scope.user_id, "n": n}
        if scope.document_ids:
            stmt = stmt.bindparams(bindparam("document_ids", expanding=True))
            params["document_ids"] = list(scope.document_ids)
        async with self._sf() as session:
            result = await session.execute(stmt, params)
            return [row_to_chunk(r) for r in result]
