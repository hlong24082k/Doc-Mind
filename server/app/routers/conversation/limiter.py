import asyncio
from typing import Callable

from fastapi import HTTPException


class ChatLimiter:
    # ponytail: giới hạn theo từng process; khi chạy nhiều replica thì giới
    # hạn thực tế = N × chat_max_concurrency. Cần giới hạn toàn cục thì dùng Redis.
    def __init__(self, max_concurrency: int, timeout_s: float):
        self._sem = asyncio.Semaphore(max_concurrency)
        self._timeout_s = timeout_s
        self._active: set[str] = set()

    async def acquire(self, user_id: str) -> Callable[[], None]:
        """429 nếu user đang có stream; 503 nếu chờ slot quá timeout.
        Trả về hàm release idempotent cho đúng lượt acquire này."""
        if user_id in self._active:
            raise HTTPException(429, "A reply is already in progress")
        self._active.add(user_id)
        try:
            await asyncio.wait_for(self._sem.acquire(), self._timeout_s)
        except TimeoutError:
            self._active.discard(user_id)
            raise HTTPException(503, "Server is busy", headers={"Retry-After": "5"})
        except BaseException:
            self._active.discard(user_id)
            raise

        released = False

        def release() -> None:
            nonlocal released
            if not released:
                released = True
                self.release(user_id)

        return release

    def release(self, user_id: str) -> None:
        self._active.discard(user_id)
        self._sem.release()
