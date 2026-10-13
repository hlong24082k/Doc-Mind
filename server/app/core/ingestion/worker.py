"""Worker ingest đọc hàng đợi Postgres (documents.status = 'pending')."""

import asyncio
from pathlib import Path
from typing import Callable

from loguru import logger

from app.core.domain import DocumentRecord
from app.core.errors import DocumentLoadError
from app.core.ingestion.pipeline import IngestionPipeline
from app.core.interfaces import DocumentStore

# Lỗi vĩnh viễn: thử lại cũng không khác → failed ngay
PERMANENT = (DocumentLoadError, FileNotFoundError)


class IngestionWorker:
    def __init__(
        self,
        pipeline: IngestionPipeline,
        documents: DocumentStore,
        resolve_path: Callable[[DocumentRecord], Path],
        *,
        concurrency: int = 2,
        poll_interval_s: float = 2.0,
        max_attempts: int = 3,
        stale_after_s: int = 900,
    ):
        self.pipeline = pipeline
        self.documents = documents
        self.resolve_path = resolve_path
        self.concurrency = concurrency
        self.poll_interval_s = poll_interval_s
        self.max_attempts = max_attempts
        # ponytail: job chạy lâu hơn stale_after_s có thể bị claim lần nữa;
        # có PDF lớn hơn mức đó thì tăng giá trị này
        self.stale_after_s = stale_after_s

    async def run_forever(self) -> None:
        # ponytail: poll mỗi poll_interval_s; LISTEN/NOTIFY nếu cần độ trễ < 1s
        sem = asyncio.Semaphore(self.concurrency)
        logger.info("Ingest worker started (concurrency={})", self.concurrency)
        async with asyncio.TaskGroup() as tg:
            while True:
                await sem.acquire()
                try:
                    job = await self.documents.claim_next(
                        stale_after_s=self.stale_after_s
                    )
                except Exception:
                    logger.exception("claim failed")
                    sem.release()
                    await asyncio.sleep(self.poll_interval_s)
                    continue
                if job is None:
                    sem.release()
                    await asyncio.sleep(self.poll_interval_s)
                    continue
                tg.create_task(self._process(job, sem))

    async def _process(self, job: DocumentRecord, sem: asyncio.Semaphore) -> None:
        """Không bao giờ raise ra ngoài (trừ CancelledError), nên một job lỗi
        không làm TaskGroup hủy các job khác."""
        try:
            if job.attempts > self.max_attempts:
                await self.documents.mark_failed(
                    job.id, f"Gave up after {self.max_attempts} attempts"
                )
                return
            logger.info("ingest {} (attempt {})", job.id, job.attempts)
            await self.pipeline.run(job, self.resolve_path(job))
        except asyncio.CancelledError:
            await asyncio.shield(self.documents.release(job.id))
            raise
        except PERMANENT as e:
            await self._safe(self.documents.mark_failed, job, e)
        except Exception as e:
            logger.exception("ingest {} failed (attempt {})", job.id, job.attempts)
            await self._safe(self.documents.requeue, job, e)
        finally:
            sem.release()

    @staticmethod
    async def _safe(update, job: DocumentRecord, e: Exception) -> None:
        # Job bị xóa giữa chừng / DB lỗi: chỉ log, không để lỗi lan ra
        try:
            await update(job.id, f"{type(e).__name__}: {e}")
        except Exception:
            logger.exception("cannot update status of {}", job.id)
