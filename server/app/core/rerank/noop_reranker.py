from typing import Sequence

from app.core.domain import ScoredChunk


class NoOpReranker:
    """Giữ nguyên thứ tự RRF, chỉ cắt top_n."""

    async def rerank(
        self,
        query: str,
        candidates: Sequence[ScoredChunk],
        top_n: int,
    ) -> list[ScoredChunk]:
        return [c.with_score("rerank", c.score) for c in candidates[:top_n]]
