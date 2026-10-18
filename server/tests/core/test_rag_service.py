from app.core.domain import ScoredChunk, SearchScope
from app.core.rag_service import RAGService

from .conftest import make_chunk


class FakeRetriever:
    def __init__(self, chunks):
        self.chunks = chunks

    async def retrieve(self, query, scope, k, timings=None):
        return self.chunks


def svc(chunks, min_dense):
    # context_builder/generator = None: nếu bị gọi tới thì test vỡ
    return RAGService(FakeRetriever(chunks), None, None, min_dense_score=min_dense)


def hit(dense=None):
    scores = {"rrf": 0.01} if dense is None else {"dense": dense, "rrf": 0.01}
    return ScoredChunk(chunk=make_chunk(1), score=0.01, scores=scores)


async def test_low_dense_score_refuses_without_llm():
    a = await svc([hit(0.5)], 0.65).answer("weather?", SearchScope("u"))
    assert a.refused and "llm" not in a.timings_ms
    assert list(a.timings_ms)[-1] == "total"


async def test_gate_passes_high_score_and_sparse_only():
    assert (await svc([hit(0.8)], 0.65).search("q", SearchScope("u"))).chunks
    assert (await svc([hit()], 0.65).search("q", SearchScope("u"))).chunks
