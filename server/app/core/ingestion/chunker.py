import re
from dataclasses import dataclass

from app.core.domain import ChunkDraft, ParsedDocument
from app.core.interfaces import TokenCounter

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")
_ABBREVIATIONS = (
    "et al.",
    "e.g.",
    "i.e.",
    "fig.",
    "figs.",
    "eq.",
    "eqs.",
    "sec.",
    "tab.",
    "vs.",
    "cf.",
    "no.",
)
_LEADING_NUMBER = re.compile(r"^(\d+(\.\d+)*\.?|[IVX]+\.)\s+")
_REFERENCE_HEADINGS = {"references", "bibliography"}


@dataclass(frozen=True, slots=True)
class _Sentence:
    text: str
    page: int
    tokens: int


@dataclass(slots=True)
class _Chunk:
    sentences: list[_Sentence]
    n_carry: int  # số câu đầu là overlap từ chunk trước


class StructuredChunker:
    """Chunk theo section, overlap theo câu, đo bằng token của ModernBERT."""

    def __init__(
        self,
        counter: TokenCounter,
        target_tokens: int = 384,
        overlap_tokens: int = 64,
        max_tokens: int = 512,
        min_tokens: int = 64,
        include_references: bool = False,
    ):
        self.counter = counter
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens
        self.include_references = include_references

    # ------------------------------------------------------------------
    def chunk(self, document: ParsedDocument) -> list[ChunkDraft]:
        drafts: list[ChunkDraft] = []
        for section, sentences in self._sections(document):
            for ch in self._pack(sentences):
                drafts.append(self._to_draft(len(drafts), section, ch))
        return drafts

    # ---- sections -----------------------------------------------------
    def _sections(self, document: ParsedDocument):
        section: str | None = None
        sentences: list[_Sentence] = []
        skipping = False
        for block in document.blocks:
            if block.is_heading:
                if sentences:
                    yield section, sentences
                    sentences = []
                name = _LEADING_NUMBER.sub("", block.text).strip().lower()
                if skipping and "appendix" in block.text.lower():
                    skipping = False
                if not self.include_references and name in _REFERENCE_HEADINGS:
                    skipping = True
                section = block.text
                continue
            if skipping:
                continue
            for text in self._split_sentences(block.text):
                sentences.extend(self._make_sentences(text, block.page_number))
        if sentences:
            yield section, sentences

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        merged: list[str] = []
        for piece in _SENTENCE_SPLIT.split(text):
            piece = piece.strip()
            if not piece:
                continue
            if merged and _ends_with_abbreviation(merged[-1]):
                merged[-1] = f"{merged[-1]} {piece}"
            else:
                merged.append(piece)
        return merged

    def _make_sentences(self, text: str, page: int) -> list[_Sentence]:
        tokens = self.counter.count(text)
        if tokens <= self.max_tokens:
            return [_Sentence(text, page, tokens)]
        return [
            _Sentence(part, page, self.counter.count(part))
            for part in self._hard_split(text)
        ]

    def _hard_split(self, text: str) -> list[str]:
        splitter = getattr(self.counter, "split_by_tokens", None)
        if splitter is not None:
            return splitter(text, self.max_tokens)
        parts: list[str] = []
        current: list[str] = []
        for word in text.split():
            candidate = " ".join(current + [word])
            if current and self.counter.count(candidate) > self.max_tokens:
                parts.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            parts.append(" ".join(current))
        return parts

    # ---- packing ------------------------------------------------------
    def _pack(self, sentences: list[_Sentence]) -> list[_Chunk]:
        chunks: list[_Chunk] = []
        cur: list[_Sentence] = []
        n_carry = 0
        cur_tok = 0
        for s in sentences:
            if len(cur) > n_carry and cur_tok + s.tokens > self.target_tokens:
                chunks.append(_Chunk(cur, n_carry))
                cur = self._tail(cur)
                n_carry = len(cur)
                cur_tok = sum(x.tokens for x in cur)
            if cur and cur_tok + s.tokens > self.max_tokens:
                cur, n_carry, cur_tok = [], 0, 0
            cur.append(s)
            cur_tok += s.tokens
        if len(cur) > n_carry:
            chunks.append(_Chunk(cur, n_carry))
        return self._merge_small_tail(chunks)

    def _tail(self, sentences: list[_Sentence]) -> list[_Sentence]:
        tail: list[_Sentence] = []
        total = 0
        for s in reversed(sentences):
            if total + s.tokens > self.overlap_tokens:
                break
            tail.append(s)
            total += s.tokens
        tail.reverse()
        return tail

    def _merge_small_tail(self, chunks: list[_Chunk]) -> list[_Chunk]:
        if len(chunks) < 2:
            return chunks
        last, prev = chunks[-1], chunks[-2]
        new_part = last.sentences[last.n_carry :]
        if sum(s.tokens for s in new_part) >= self.min_tokens:
            return chunks
        merged = _Chunk(prev.sentences + new_part, prev.n_carry)
        if self.counter.count(_join(merged.sentences)) > self.max_tokens:
            return chunks
        return chunks[:-2] + [merged]

    # ---- draft --------------------------------------------------------
    def _to_draft(self, index: int, section: str | None, ch: _Chunk) -> ChunkDraft:
        content = _join(ch.sentences)
        tokens = self.counter.count(content)
        n_carry = ch.n_carry
        if tokens > self.max_tokens and n_carry:
            # tokenization không cộng tính được: bỏ overlap để giữ giới hạn
            n_carry = 0
            content = _join(ch.sentences[ch.n_carry :])
            tokens = self.counter.count(content)
        overlap_chars = len(_join(ch.sentences[:n_carry])) + 1 if n_carry else 0
        pages = [s.page for s in ch.sentences]
        return ChunkDraft(
            chunk_index=index,
            content=content,
            section=section,
            page_start=min(pages),
            page_end=max(pages),
            token_count=tokens,
            overlap_chars=overlap_chars,
        )


def _join(sentences: list[_Sentence]) -> str:
    return " ".join(s.text for s in sentences)


def _ends_with_abbreviation(text: str) -> bool:
    lower = text.lower()
    for abbr in _ABBREVIATIONS:
        if lower.endswith(abbr) and (
            len(lower) == len(abbr) or not lower[-len(abbr) - 1].isalnum()
        ):
            return True
    return False
