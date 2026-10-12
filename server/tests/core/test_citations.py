from app.core.domain import ContextBlock
from app.core.generation.citations import (
    build_citations,
    is_grounded,
    parse_refs,
)
from app.core.prompt.rag_prompts import REFUSAL_TEXT


def ctx(ref: int) -> ContextBlock:
    return ContextBlock(
        ref=ref,
        document_id=f"d{ref}",
        document_name=f"doc{ref}",
        page_start=ref,
        page_end=ref + 1,
        section=None,
        text="x",
        chunk_ids=(ref,),
    )


def check(text: str, n: int = 3):
    citations, invalid = build_citations(text, [ctx(i) for i in range(1, n + 1)])
    return citations, invalid, is_grounded(text, citations, invalid)


def test_parse_refs_order_and_dedupe():
    assert parse_refs("A [1][3]. B [3] and [2] then [1].") == [1, 3, 2]


def test_valid_citations_are_grounded():
    citations, invalid, grounded = check("Fact [1][3].")
    assert [c.ref for c in citations] == [1, 3]
    assert citations[0].document_name == "doc1"
    assert (citations[0].page_start, citations[0].page_end) == (1, 2)
    assert invalid == [] and grounded


def test_invalid_ref_is_detected():
    citations, invalid, grounded = check("Fact [1] and [7].")
    assert invalid == [7]
    assert [c.ref for c in citations] == [1]
    assert not grounded


def test_refusal_is_grounded_without_citations():
    _, _, grounded = check(REFUSAL_TEXT)
    assert grounded


def test_answer_without_citation_not_grounded():
    citations, invalid, grounded = check("Plain statement.")
    assert citations == [] and invalid == []
    assert not grounded
