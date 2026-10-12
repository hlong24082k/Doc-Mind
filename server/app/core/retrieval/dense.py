import time

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.domain import ScoredChunk, SearchScope
from app.core.interfaces import Embedder
from app.core.storage.chunk_repository import row_to_chunk


class PgVectorRetriever:
    """Dense retrieval bằng pgvector HNSW (cosine)."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        embedder: Embedder,
        ef_search: int = 100,
    ):
        self._sf = session_factory
        self.embedder = embedder
        self.ef_search = int(ef_search)

    async def retrieve(
        self,
        query: str,
        scope: SearchScope,
        k: int,
        timings: dict[str, float] | None = None,
    ) -> list[ScoredChunk]:
        if not query.strip():
            return []
        timings = {} if timings is None else timings
        t = time.perf_counter()
        vector = await self.embedder.embed_query(query)
        timings["embed_query"] = (time.perf_counter() - t) * 1000
        qvec = "[" + ",".join(repr(float(x)) for x in vector) + "]"

        doc_filter = "AND document_id IN :document_ids" if scope.document_ids else ""
        stmt = text(f"""
            WITH nn AS MATERIALIZED (
              SELECT id, embedding <=> CAST(:qvec AS vector) AS distance
              FROM document_chunks
              WHERE user_id = :user_id
                {doc_filter}
              ORDER BY embedding <=> CAST(:qvec AS vector)
              LIMIT :k
            )
            SELECT c.id, c.document_id, d.name AS document_name,
                   d.title AS document_title, c.chunk_index, c.content,
                   c.section, c.page_start, c.page_end, c.overlap_chars,
                   1 - nn.distance AS score
            FROM nn
            JOIN document_chunks c ON c.id = nn.id
            JOIN documents d ON d.id = c.document_id
            ORDER BY nn.distance, c.id
            """)
        params: dict = {"qvec": qvec, "user_id": scope.user_id, "k": k}
        if scope.document_ids:
            stmt = stmt.bindparams(bindparam("document_ids", expanding=True))
            params["document_ids"] = list(scope.document_ids)

        t = time.perf_counter()
        async with self._sf() as session:
            async with session.begin():
                # SET LOCAL không nhận bind param; ef_search đã ép kiểu int
                await session.execute(
                    text(f"SET LOCAL hnsw.ef_search = {self.ef_search}")
                )
                await session.execute(
                    text("SET LOCAL hnsw.iterative_scan = relaxed_order")
                )
                rows = (await session.execute(stmt, params)).all()
        timings["dense"] = (time.perf_counter() - t) * 1000

        return [
            ScoredChunk(
                chunk=row_to_chunk(r),
                score=float(r.score),
                scores={"dense": float(r.score)},
                ranks={"dense": i + 1},
            )
            for i, r in enumerate(rows)
        ]
