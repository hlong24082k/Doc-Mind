import asyncio
from typing import Sequence

from app.core.domain import ContextBlock, RetrievedChunk, ScoredChunk
from app.core.interfaces import ChunkReader, TokenCounter


class ContextBuilder:
    """Small-to-big: mở rộng chunk ±window, gộp, đánh số nguồn."""

    def __init__(
        self,
        chunk_reader: ChunkReader,
        counter: TokenCounter,
        window: int = 1,
        max_tokens: int = 6000,
    ):
        self.chunk_reader = chunk_reader
        self.counter = counter
        self.window = window
        self.max_tokens = max_tokens

    async def build(self, chunks: Sequence[ScoredChunk]) -> list[ContextBlock]:
        # (document_id, first, last, best_rank)
        spans: list[list] = []
        for rank, sc in enumerate(chunks):
            c = sc.chunk
            lo = max(0, c.chunk_index - self.window)
            hi = c.chunk_index + self.window
            spans.append([c.document_id, lo, hi, rank])

        merged = self._merge(spans)
        merged.sort(key=lambda s: s[3])

        known = {
            (sc.chunk.document_id, sc.chunk.chunk_index): sc.chunk for sc in chunks
        }

        async def fetch(doc_id: str, lo: int, hi: int) -> list[RetrievedChunk]:
            have = [known.get((doc_id, i)) for i in range(lo, hi + 1)]
            if all(have):  # window=0 (hoặc đã có đủ chunk): không cần DB
                return have
            return await self.chunk_reader.get_window(doc_id, lo, hi)

        windows = await asyncio.gather(*(fetch(d, lo, hi) for d, lo, hi, _ in merged))

        blocks: list[ContextBlock] = []
        used = 0
        for window in windows:
            if not window:
                continue
            block = self._to_block(len(blocks) + 1, window)
            tokens = self.counter.count(block.text)
            if blocks and used + tokens > self.max_tokens:
                continue
            blocks.append(block)
            used += tokens
        return blocks

    @staticmethod
    def _merge(spans: list[list]) -> list[list]:
        by_doc: dict[str, list[list]] = {}
        for s in spans:
            by_doc.setdefault(s[0], []).append(s)
        out: list[list] = []
        for doc_id, items in by_doc.items():
            items.sort(key=lambda s: s[1])
            cur = list(items[0])
            for s in items[1:]:
                if s[1] <= cur[2] + 1:  # giao nhau hoặc liền kề
                    cur[2] = max(cur[2], s[2])
                    cur[3] = min(cur[3], s[3])
                else:
                    out.append(cur)
                    cur = list(s)
            out.append(cur)
        return out

    @staticmethod
    def _to_block(ref: int, window: list[RetrievedChunk]) -> ContextBlock:
        text = window[0].content
        for c in window[1:]:
            # overlap_chars đã gồm dấu cách nối; chunk không overlap
            # (section mới) thì ngăn cách bằng đoạn mới
            if c.overlap_chars:
                text += " " + c.content[c.overlap_chars :]
            else:
                text += "\n\n" + c.content
        first = window[0]
        return ContextBlock(
            ref=ref,
            document_id=first.document_id,
            document_name=first.document_name,
            document_title=first.document_title,
            page_start=min(c.page_start for c in window),
            page_end=max(c.page_end for c in window),
            section=first.section,
            text=text,
            chunk_ids=tuple(c.chunk_id for c in window),
        )
