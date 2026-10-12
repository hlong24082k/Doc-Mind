from typing import Mapping, Sequence

from app.core.domain import ScoredChunk


class ReciprocalRankFusion:
    """RRF: score(id) = Σ weight_b / (k + rank_b(id)), rank từ 1."""

    def __init__(
        self,
        k: int = 60,
        weights: Mapping[str, float] | None = None,
    ):
        self.k = k
        self.weights = dict(weights or {})

    def fuse(
        self, ranked: Mapping[str, Sequence[ScoredChunk]], k: int
    ) -> list[ScoredChunk]:
        fused: dict[int, ScoredChunk] = {}
        rrf: dict[int, float] = {}
        for branch, items in ranked.items():
            weight = self.weights.get(branch, 1.0)
            for rank, item in enumerate(items, start=1):
                cid = item.chunk.chunk_id
                rrf[cid] = rrf.get(cid, 0.0) + weight / (self.k + rank)
                prev = fused.get(cid)
                scores = {**(prev.scores if prev else {})}
                ranks = {**(prev.ranks if prev else {})}
                scores[branch] = item.scores.get(branch, item.score)
                ranks[branch] = rank
                fused[cid] = ScoredChunk(
                    chunk=item.chunk, score=0.0, scores=scores, ranks=ranks
                )

        out = [fused[cid].with_score("rrf", score) for cid, score in rrf.items()]
        out.sort(key=lambda s: (-s.scores["rrf"], s.chunk.chunk_id))
        return out[:k]
