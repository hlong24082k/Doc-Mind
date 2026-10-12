from app.core.domain import RetrievedChunk, ScoredChunk


class FakeTokenCounter:
    """Đếm token theo từ."""

    def count(self, text: str) -> int:
        return len(text.split())


def make_chunk(
    chunk_id: int,
    *,
    doc: str = "d1",
    index: int | None = None,
    content: str = "text",
    overlap: int = 0,
    pages: tuple[int, int] = (1, 1),
    section: str | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=doc,
        document_name=doc,
        document_title=None,
        chunk_index=chunk_id if index is None else index,
        content=content,
        section=section,
        page_start=pages[0],
        page_end=pages[1],
        overlap_chars=overlap,
    )


def scored(chunk_id: int, branch: str, score: float = 1.0, **kw):
    return ScoredChunk(
        chunk=make_chunk(chunk_id, **kw),
        score=score,
        scores={branch: score},
        ranks={},
    )
