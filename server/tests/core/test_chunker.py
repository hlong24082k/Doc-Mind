from app.core.domain import ParsedDocument, TextBlock
from app.core.ingestion.chunker import StructuredChunker

from .conftest import FakeTokenCounter


def sentence(i: int, words: int = 10) -> str:
    return f"S{i} " + " ".join(f"w{i}x{j}" for j in range(words - 2)) + " end."


def para(start: int, n: int, words: int = 10) -> str:
    return " ".join(sentence(i, words) for i in range(start, start + n))


def doc(*blocks: tuple[str, bool]) -> ParsedDocument:
    return ParsedDocument("T", 1, tuple(TextBlock(1, t, h) for t, h in blocks))


def make(**kw) -> StructuredChunker:
    params = dict(target_tokens=40, overlap_tokens=12, max_tokens=60, min_tokens=15)
    params.update(kw)
    return StructuredChunker(FakeTokenCounter(), **params)


def test_max_tokens_invariant_and_reconstruction():
    text = para(0, 30)
    chunks = make().chunk(doc(("Intro", True), (text, False)))
    assert len(chunks) > 1
    assert all(c.token_count <= 60 for c in chunks)
    rebuilt = chunks[0].content
    for c in chunks[1:]:
        rebuilt += " " + c.content[c.overlap_chars :]
    assert rebuilt.split() == text.split()


def test_overlap_repeats_tail_of_previous_chunk():
    chunks = make().chunk(doc(("Intro", True), (para(0, 20), False)))
    for prev, cur in zip(chunks, chunks[1:]):
        assert cur.overlap_chars > 0
        overlap = cur.content[: cur.overlap_chars].strip()
        assert prev.content.endswith(overlap)
        assert len(overlap.split()) <= 12


def test_no_overlap_across_sections():
    chunks = make().chunk(
        doc(
            ("A", True),
            (para(0, 6), False),
            ("B", True),
            (para(100, 6), False),
        )
    )
    first_b = next(c for c in chunks if c.section == "B")
    assert first_b.overlap_chars == 0
    assert chunks[0].section == "A"
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_references_skipped_until_appendix():
    chunks = make().chunk(
        doc(
            ("1 Introduction", True),
            (para(0, 3), False),
            ("References", True),
            (para(50, 3), False),
            ("Appendix A", True),
            (para(80, 3), False),
        )
    )
    text = " ".join(c.content for c in chunks)
    assert "S0 " in text and "S80 " in text
    assert "S50 " not in text
    assert {c.section for c in chunks} == {"1 Introduction", "Appendix A"}


def test_references_kept_when_enabled():
    chunks = make(include_references=True).chunk(
        doc(("References", True), (para(50, 3), False))
    )
    assert "S50 " in chunks[0].content


def test_small_tail_is_merged():
    # 4 câu x 10 từ = 40: đủ 1 chunk, câu thứ 5 là đuôi 10 từ < min 15
    chunks = make(overlap_tokens=0).chunk(doc(("A", True), (para(0, 5), False)))
    assert len(chunks) == 1
    assert chunks[0].token_count == 50


def test_very_long_sentence_is_hard_split():
    long_sentence = "Start " + " ".join(f"t{i}" for i in range(149)) + " end."
    chunks = make().chunk(doc(("A", True), (long_sentence, False)))
    assert len(chunks) >= 3
    assert all(c.token_count <= 60 for c in chunks)


def test_abbreviations_do_not_split_sentences():
    text = "We follow Vaswani et al. Results are in Fig. 3 and Eq. 2 here."
    chunker = make()
    assert chunker._split_sentences(text) == [text]
