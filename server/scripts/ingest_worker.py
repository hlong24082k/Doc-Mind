"""Chạy ingest worker thành process riêng để scale ngang.

Chạy: cd server && INGEST_WORKER_ENABLED=false (trên API) rồi
      uv run python scripts/ingest_worker.py
"""

import asyncio
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, SERVER_DIR)

from app.core.factory import build_ingest_worker  # noqa: E402
from app.db.session import engine  # noqa: E402


async def main() -> None:
    try:
        await build_ingest_worker().run_forever()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())  # Ctrl+C → hủy task → job đang dở về pending
    except KeyboardInterrupt:
        pass
