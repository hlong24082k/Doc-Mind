import pytest

from app.core.domain import ScoredChunk
from app.core.generation.context_builder import ContextBuilder

from .conftest import FakeTokenCounter, make_chunk


class FakeReader:
    def __init__(self, chunks):
        self.chunks = chunks

    async def get_window(self, document_id, first, last):
        return sorted(
            (
                c
                for c in self.chunks
                if c.document_id == document_id and first <= c.chunk_index <= last
            ),
            key=lambda c: c.chunk_index,
        )

    async def sample(self, scope, n):
        return []


def corpus(doc="d1", n=10):
    """Chunk i = 'a{i} b{i} c{i}'; chunk i>0 overlap 1 từ cuối chunk i-1."""
    chunks = []
    for i in range(n):
        words = [f"a{i}", f"b{i}", f"c{i}"]
        overlap = 0
        if i > 0:
            words = [f"c{i-1}"] + words
            overlap = len(f"c{i-1}") + 1
        chunks.append(
            make_chunk(
                i + (100 if doc == "d2" else 0),
                doc=doc,
                index=i,
                content=" ".join(words),
                overlap=overlap,
                pages=(i + 1, i + 1),
            )
        )
    return chunks


def hit(chunks, idx):
    return ScoredChunk(chunk=chunks[idx], score=1.0)


def builder(chunks, **kw):
    return ContextBuilder(FakeReader(chunks), FakeTokenCounter(), **kw)


@pytest.mark.asyncio
async def test_merges_adjacent_windows_without_duplicate_overlap():
    chunks = corpus()
    blocks = await builder(chunks, window=1).build([hit(chunks, 3), hit(chunks, 5)])
    assert len(blocks) == 1  # [2..4] và [4..6] giao nhau
    words = blocks[0].text.split()
    # chunk đầu giữ overlap của nó (c1), các chunk sau không lặp lại
    assert words == ["c1"] + [
        w for i in range(2, 7) for w in (f"a{i}", f"b{i}", f"c{i}")
    ]
    assert blocks[0].page_start == 3 and blocks[0].page_end == 7
    assert blocks[0].ref == 1


@pytest.mark.asyncio
async def test_order_follows_input_and_refs_numbered():
    chunks = corpus()
    blocks = await builder(chunks, window=0).build([hit(chunks, 8), hit(chunks, 1)])
    assert [b.ref for b in blocks] == [1, 2]
    assert blocks[0].chunk_ids == (8,)
    assert blocks[1].chunk_ids == (1,)


@pytest.mark.asyncio
async def test_separate_documents_not_merged():
    d1, d2 = corpus("d1"), corpus("d2")
    blocks = await builder(d1 + d2, window=1).build([hit(d1, 3), hit(d2, 3)])
    assert len(blocks) == 2
    assert {b.document_id for b in blocks} == {"d1", "d2"}


@pytest.mark.asyncio
async def test_token_budget_drops_later_blocks_but_keeps_first():
    chunks = corpus()
    b = builder(chunks, window=0, max_tokens=5)
    blocks = await b.build([hit(chunks, 1), hit(chunks, 7), hit(chunks, 9)])
    assert len(blocks) == 1
    assert blocks[0].chunk_ids == (1,)

    tiny = builder(chunks, window=0, max_tokens=1)
    assert len(await tiny.build([hit(chunks, 1)])) == 1


class NoDBReader(FakeReader):
    async def get_window(self, document_id, first, last):
        raise AssertionError("window=0 không được query DB")


@pytest.mark.asyncio
async def test_window_zero_skips_db():
    chunks = corpus()
    b = ContextBuilder(NoDBReader(chunks), FakeTokenCounter(), window=0)
    blocks = await b.build([hit(chunks, 3), hit(chunks, 4), hit(chunks, 8)])
    assert [blk.chunk_ids for blk in blocks] == [(3, 4), (8,)]
    assert blocks[0].text.split() == ["c2", "a3", "b3", "c3", "a4", "b4", "c4"]
