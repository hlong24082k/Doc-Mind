import asyncio
import time

from app.core.domain import ScoredChunk, SearchScope
from app.core.interfaces import FusionStrategy, Retriever


class HybridRetriever:
    """Dense + sparse chạy song song, gộp bằng fusion strategy."""

    def __init__(
        self,
        dense: Retriever,
        sparse: Retriever,
        fusion: FusionStrategy,
        dense_k: int = 50,
        sparse_k: int = 50,
    ):
        self.dense = dense
        self.sparse = sparse
        self.fusion = fusion
        self.dense_k = dense_k
        self.sparse_k = sparse_k

    async def retrieve(
        self,
        query: str,
        scope: SearchScope,
        k: int,
        timings: dict[str, float] | None = None,
    ) -> list[ScoredChunk]:
        dense, sparse = await asyncio.gather(
            self.dense.retrieve(query, scope, self.dense_k, timings),
            self.sparse.retrieve(query, scope, self.sparse_k, timings),
        )
        t = time.perf_counter()
        fused = self.fusion.fuse({"dense": dense, "sparse": sparse}, k)
        if timings is not None:
            timings["fusion"] = (time.perf_counter() - t) * 1000
        return fused
