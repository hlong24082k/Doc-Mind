"""Các kiểm tra chạy TRƯỚC khi đọc body upload."""

import asyncio
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import HTTPException, Request


class UploadLimiter:
    # ponytail: giới hạn theo từng process; khi chạy nhiều replica thì giới
    # hạn thực tế = N × upload_max_concurrency
    def __init__(self, max_concurrency: int):
        self._sem = asyncio.Semaphore(max_concurrency)

    @asynccontextmanager
    async def slot(self):
        if self._sem.locked():  # không chờ: trả 503 ngay để client thử lại
            raise HTTPException(503, "Too many uploads", headers={"Retry-After": "5"})
        async with self._sem:  # không có await giữa check và acquire → không race
            yield


def check_content_length(request: Request, max_bytes: int) -> int:
    """Content-Length là cận trên tin được: uvicorn chỉ đọc đúng số byte đã
    khai báo. Request chunked (không có header) → 411."""
    raw = request.headers.get("content-length")
    if raw is None:
        raise HTTPException(411, "Content-Length required")
    try:
        length = int(raw)
    except ValueError:
        raise HTTPException(400, "Invalid Content-Length")
    if length > max_bytes:
        raise HTTPException(413, "Upload is too large")
    return length


async def check_disk_free(folder: Path, incoming: int, min_free: int) -> None:
    free = (await asyncio.to_thread(shutil.disk_usage, folder)).free
    if free - incoming < min_free:
        raise HTTPException(507, "Insufficient storage")
