import re
from typing import Sequence

from app.core.domain import Citation, ContextBlock
from app.core.prompt.rag_prompts import REFUSAL_TEXT

_REF = re.compile(r"\[(\d+)\]")


def parse_refs(text: str) -> list[int]:
    """Các số [n] theo thứ tự xuất hiện đầu tiên, bỏ trùng."""
    seen: list[int] = []
    for m in _REF.finditer(text):
        n = int(m.group(1))
        if n not in seen:
            seen.append(n)
    return seen


def build_citations(
    text: str, contexts: Sequence[ContextBlock]
) -> tuple[list[Citation], list[int]]:
    by_ref = {c.ref: c for c in contexts}
    citations: list[Citation] = []
    invalid: list[int] = []
    for ref in parse_refs(text):
        block = by_ref.get(ref)
        if block is None:
            invalid.append(ref)
            continue
        citations.append(
            Citation(
                ref=ref,
                document_id=block.document_id,
                document_name=block.document_name,
                page_start=block.page_start,
                page_end=block.page_end,
            )
        )
    return citations, invalid


def is_refusal(text: str) -> bool:
    return text.strip().strip('"') == REFUSAL_TEXT


def is_grounded(
    text: str, citations: Sequence[Citation], invalid_refs: Sequence[int]
) -> bool:
    if is_refusal(text):
        return True
    return len(citations) >= 1 and not invalid_refs
