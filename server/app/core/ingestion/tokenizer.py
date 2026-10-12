from tokenizers import Tokenizer


class HFTokenCounter:
    """Đếm token theo tokenizer HuggingFace (ModernBERT, khớp với Laya)."""

    def __init__(self, model_id: str):
        self._tokenizer = Tokenizer.from_pretrained(model_id)
        self._tokenizer.no_truncation()

    def count(self, text: str) -> int:
        return len(self._tokenizer.encode(text, add_special_tokens=False).ids)

    def split_by_tokens(self, text: str, max_tokens: int) -> list[str]:
        """Cắt cứng text thành các đoạn ≤ max_tokens (theo offsets)."""
        enc = self._tokenizer.encode(text, add_special_tokens=False)
        offsets = enc.offsets
        parts: list[str] = []
        for i in range(0, len(offsets), max_tokens):
            window = offsets[i : i + max_tokens]
            start, end = window[0][0], window[-1][1]
            piece = text[start:end].strip()
            if piece:
                parts.append(piece)
        return parts
