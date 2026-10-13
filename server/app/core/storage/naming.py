import re
import unicodedata

_FORBIDDEN = re.compile(r'[/\\:*?"<>|]')
_PDF_SUFFIX = re.compile(r"\.pdf$", re.IGNORECASE)


def canonical_document_name(filename: str | None, max_bytes: int = 200) -> str | None:
    """Tên document an toàn để làm tên file trên APFS / ext4.
    1. NFC     : browser trên macOS có thể gửi NFD; APFS coi NFC == NFD.
    2. basename: cắt theo cả '/' và '\\' (Path.name không cắt '\\' trên POSIX).
    3. bỏ đuôi '.pdf' (không phân biệt hoa/thường).
    4. ký tự điều khiển (category C*) và / \\ : * ? " < > |  →  '_'.
    5. gộp whitespace; strip ' ' và '.' ở 2 đầu (không hidden file, không '..').
    6. cắt ≤ max_bytes UTF-8 tại ranh giới ký tự (ext4 giới hạn 255 *byte*;
       tiếng Việt 2-3 byte/ký tự), strip lại.
    Rỗng → None."""
    # ponytail: lower() của Postgres và case-folding của APFS khác nhau ở vài
    # ký tự hiếm (ß, İ); gặp thì thêm casefold() vào đây.
    if not filename:
        return None
    name = unicodedata.normalize("NFC", filename)
    name = re.split(r"[/\\]", name)[-1]
    name = _PDF_SUFFIX.sub("", name)
    name = "".join(
        "_" if unicodedata.category(ch).startswith("C") else ch for ch in name
    )
    name = _FORBIDDEN.sub("_", name)
    name = " ".join(name.split()).strip(" .")
    encoded = name.encode("utf-8")[:max_bytes]
    name = encoded.decode("utf-8", errors="ignore").strip(" .")
    return name or None
