# flake8: noqa: E501
from typing import Sequence

from app.core.domain import ContextBlock

REFUSAL_TEXT = "I couldn't find information about this in the provided documents."

RAG_SYSTEM_PROMPT = """You are Doc-Mind, an assistant that answers questions strictly from the provided document excerpts.

Rules:
1. Use ONLY the information in the numbered sources below. Do not use prior knowledge.
2. Every factual sentence MUST end with at least one citation in the form [n], where n is the source number. Use multiple citations like [1][3] when combining sources.
3. If the sources do not contain the answer, reply exactly: "{refusal}"
4. Do not invent source numbers. Do not cite a source that does not support the sentence.
5. Answer in the same language as the question. Be concise and precise; prefer the paper's own terminology.
""".format(
    refusal=REFUSAL_TEXT
)


def _format_header(block: ContextBlock) -> str:
    name = block.document_title or block.document_name
    pages = (
        f"page {block.page_start}"
        if block.page_start == block.page_end
        else f"pages {block.page_start}-{block.page_end}"
    )
    header = f'[{block.ref}] "{name}", {pages}'
    if block.section:
        header += f', section "{block.section}"'
    return header


def build_rag_user_prompt(question: str, contexts: Sequence[ContextBlock]) -> str:
    sources = "\n\n".join(f"{_format_header(b)}\n{b.text}" for b in contexts)
    return f"Sources:\n{sources}\n\nQuestion: {question}"
