import re
import unicodedata
from collections import Counter
from pathlib import Path

import pymupdf

from app.core.domain import ParsedDocument, TextBlock
from app.core.errors import DocumentLoadError

_NUMBERED_HEADING = re.compile(r"^(\d+(\.\d+)*\.?|[IVX]+\.)\s+[A-Z]")
_LEADING_NUMBER = re.compile(r"^(\d+(\.\d+)*\.?|[IVX]+\.)\s+")
_KNOWN_HEADINGS = {
    "abstract",
    "introduction",
    "related work",
    "background",
    "method",
    "methods",
    "methodology",
    "experiments",
    "results",
    "discussion",
    "conclusion",
    "conclusions",
    "references",
    "bibliography",
    "acknowledgments",
    "acknowledgements",
    "appendix",
}
_MIN_TEXT_CHARS = 200


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\x00", "")
    return re.sub(r"\s+", " ", text).strip()


def _is_known_heading(text: str) -> bool:
    return _LEADING_NUMBER.sub("", text).strip().lower() in _KNOWN_HEADINGS


class _RawBlock:
    __slots__ = ("page", "text", "max_size", "n_lines", "y0", "y1", "chars")

    def __init__(self, page, text, max_size, n_lines, y0, y1, chars):
        self.page = page
        self.text = text
        self.max_size = max_size
        self.n_lines = n_lines
        self.y0 = y0
        self.y1 = y1
        self.chars = chars


class PyMuPDFLoader:
    """Parse PDF (paper tiếng Anh) thành các TextBlock có đánh dấu heading."""

    def __init__(
        self,
        header_footer_margin: float = 0.06,
        repeat_threshold: float = 0.5,
    ):
        self.header_footer_margin = header_footer_margin
        self.repeat_threshold = repeat_threshold

    def load(self, path: Path) -> ParsedDocument:
        path = Path(path)
        try:
            doc = pymupdf.open(path)
        except Exception as e:
            raise DocumentLoadError(f"Không mở được PDF {path.name}: {e}")
        try:
            if doc.needs_pass or doc.is_encrypted:
                raise DocumentLoadError(f"PDF {path.name} bị mã hóa")
            return self._parse(doc, path)
        except DocumentLoadError:
            raise
        except Exception as e:
            raise DocumentLoadError(f"Lỗi đọc PDF {path.name}: {e}") from e
        finally:
            doc.close()

    # ------------------------------------------------------------------
    def _parse(self, doc: "pymupdf.Document", path: Path) -> ParsedDocument:
        flags = pymupdf.TEXT_DEHYPHENATE | pymupdf.TEXT_PRESERVE_WHITESPACE
        raw: list[_RawBlock] = []
        page_heights: dict[int, float] = {}
        first_page_spans: list[tuple[float, str, float]] = []

        for page in doc:
            pno = page.number + 1
            height = page.rect.height
            page_heights[pno] = height
            data = page.get_text("dict", flags=flags, sort=True)
            for block in data["blocks"]:
                if block.get("type") != 0:
                    continue
                lines, max_size, chars = [], 0.0, 0
                for line in block["lines"]:
                    spans = [s for s in line["spans"] if s["text"].strip()]
                    if not spans:
                        continue
                    lines.append("".join(s["text"] for s in line["spans"]))
                    for s in spans:
                        max_size = max(max_size, s["size"])
                        chars += len(s["text"])
                        if pno == 1:
                            first_page_spans.append(
                                (s["size"], _clean(s["text"]), s["bbox"][1])
                            )
                text = _clean(" ".join(lines))
                if not text:
                    continue
                raw.append(
                    _RawBlock(
                        pno,
                        text,
                        max_size,
                        len(lines),
                        block["bbox"][1],
                        block["bbox"][3],
                        chars,
                    )
                )

        raw = self._drop_header_footer(raw, page_heights, doc.page_count)

        size_weight: Counter = Counter()
        for b in raw:
            size_weight[round(b.max_size, 1)] += b.chars
        body_size = size_weight.most_common(1)[0][0] if size_weight else 0.0

        blocks = tuple(
            TextBlock(b.page, b.text, self._is_heading(b, body_size)) for b in raw
        )
        if sum(len(b.text) for b in blocks) < _MIN_TEXT_CHARS:
            raise DocumentLoadError("PDF có vẻ là bản scan, chưa hỗ trợ OCR")
        title = self._title(doc, path, first_page_spans, page_heights)
        return ParsedDocument(title=title, num_pages=doc.page_count, blocks=blocks)

    def _drop_header_footer(
        self,
        raw: list[_RawBlock],
        heights: dict[int, float],
        num_pages: int,
    ) -> list[_RawBlock]:
        margin = self.header_footer_margin

        def in_margin(b: _RawBlock) -> bool:
            h = heights[b.page]
            return b.y1 <= h * margin or b.y0 >= h * (1 - margin)

        def key(b: _RawBlock) -> str:
            return re.sub(r"\d+", "", b.text).strip().lower()

        counts: Counter = Counter()
        pages_seen: dict[str, set[int]] = {}
        for b in raw:
            if in_margin(b):
                pages_seen.setdefault(key(b), set()).add(b.page)
        for k, pages in pages_seen.items():
            counts[k] = len(pages)

        kept = []
        for b in raw:
            if in_margin(b):
                if re.fullmatch(r"\d+", b.text):
                    continue
                k = key(b)
                if k and counts[k] >= self.repeat_threshold * num_pages:
                    continue
            kept.append(b)
        return kept

    @staticmethod
    def _is_heading(b: _RawBlock, body_size: float) -> bool:
        if b.n_lines != 1 or len(b.text) > 120:
            return False
        return (
            (body_size > 0 and b.max_size >= body_size * 1.15)
            or bool(_NUMBERED_HEADING.match(b.text))
            or _is_known_heading(b.text)
        )

    @staticmethod
    def _title(doc, path: Path, spans, heights) -> str:
        meta = (doc.metadata or {}).get("title") or ""
        meta = meta.strip()
        if meta and meta.lower() not in {"untitled", path.stem.lower()}:
            if meta.lower() != path.name.lower():
                return meta
        half = heights.get(1, 0) / 2
        candidates = [(s, t) for s, t, y in spans if t and y <= half]
        if candidates:
            top = max(s for s, _ in candidates)
            title = " ".join(t for s, t in candidates if s == top)
            if title.strip():
                return title.strip()
        return path.stem
