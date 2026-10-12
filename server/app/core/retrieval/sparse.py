import time

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.domain import ScoredChunk, SearchScope
from app.core.storage.chunk_repository import row_to_chunk


class ParadeDBBM25Retriever:
    """Sparse retrieval bằng BM25 của ParadeDB (pg_search)."""

    def __init__(self, session_factory: async_sessionmaker):
        self._sf = session_factory

    async def retrieve(
        self,
        query: str,
        scope: SearchScope,
        k: int,
        timings: dict[str, float] | None = None,
    ) -> list[ScoredChunk]:
        if not query.strip():
            return []
        doc_filter = "AND document_id IN :document_ids" if scope.document_ids else ""
        stmt = text(f"""
            WITH hits AS (
              SELECT id, pdb.score(id) AS score
              FROM document_chunks
              WHERE content ||| CAST(:q AS text)
                AND user_id = :user_id
                {doc_filter}
              ORDER BY pdb.score(id) DESC, id
              LIMIT :k
            )
            SELECT c.id, c.document_id, d.name AS document_name,
                   d.title AS document_title, c.chunk_index, c.content,
                   c.section, c.page_start, c.page_end, c.overlap_chars,
                   hits.score AS score
            FROM hits
            JOIN document_chunks c ON c.id = hits.id
            JOIN documents d ON d.id = c.document_id
            ORDER BY hits.score DESC, c.id
            """)
        params: dict = {"q": query, "user_id": scope.user_id, "k": k}
        if scope.document_ids:
            stmt = stmt.bindparams(bindparam("document_ids", expanding=True))
            params["document_ids"] = list(scope.document_ids)

        t = time.perf_counter()
        async with self._sf() as session:
            rows = (await session.execute(stmt, params)).all()
        if timings is not None:
            timings["sparse"] = (time.perf_counter() - t) * 1000

        return [
            ScoredChunk(
                chunk=row_to_chunk(r),
                score=float(r.score),
                scores={"sparse": float(r.score)},
                ranks={"sparse": i + 1},
            )
            for i, r in enumerate(rows)
        ]
