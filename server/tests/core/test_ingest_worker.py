import asyncio
from pathlib import Path

from app.core.domain import DocumentRecord, DocumentStatus
from app.core.errors import DocumentLoadError
from app.core.ingestion.worker import IngestionWorker


def job(i: int, attempts: int = 1) -> DocumentRecord:
    return DocumentRecord(
        id=f"d{i}",
        user_id="u",
        name=f"n{i}",
        title=None,
        status=DocumentStatus.PROCESSING,
        content_hash="h",
        num_chunks=0,
        attempts=attempts,
    )


class FakeStore:
    def __init__(self, jobs, claim_errors: int = 0):
        self.jobs = list(jobs)
        self.claim_errors = claim_errors
        self.calls: list[tuple[str, str]] = []

    async def claim_next(self, *, stale_after_s):
        if self.claim_errors:
            self.claim_errors -= 1
            raise RuntimeError("db down")
        return self.jobs.pop(0) if self.jobs else None

    async def mark_failed(self, document_id, error):
        self.calls.append(("failed", document_id))

    async def requeue(self, document_id, error):
        self.calls.append(("requeue", document_id))

    async def release(self, document_id):
        self.calls.append(("release", document_id))


class FakePipeline:
    def __init__(self, error: Exception | None = None, delay: float = 0.01):
        self.error = error
        self.delay = delay
        self.running = 0
        self.peak = 0
        self.done: list[str] = []
        self.started = asyncio.Event()

    async def run(self, doc, path):
        self.running += 1
        self.peak = max(self.peak, self.running)
        self.started.set()
        try:
            await asyncio.sleep(self.delay)
            if self.error:
                raise self.error
            self.done.append(doc.id)
        finally:
            self.running -= 1


def worker(store, pipeline, **kw) -> IngestionWorker:
    return IngestionWorker(
        pipeline,
        store,
        lambda d: Path(d.name),
        poll_interval_s=0.001,
        **kw,
    )


async def run_for(w: IngestionWorker, seconds: float) -> None:
    task = asyncio.create_task(w.run_forever())
    await asyncio.sleep(seconds)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_never_exceeds_concurrency():
    store = FakeStore([job(i) for i in range(10)])
    pipeline = FakePipeline(delay=0.02)
    await run_for(worker(store, pipeline, concurrency=3), 0.3)
    assert pipeline.peak == 3
    assert len(pipeline.done) == 10


async def test_load_error_is_permanent():
    store = FakeStore([job(1)])
    await run_for(worker(store, FakePipeline(DocumentLoadError("scan"))), 0.1)
    assert store.calls == [("failed", "d1")]


async def test_transient_error_requeues():
    store = FakeStore([job(1)])
    await run_for(worker(store, FakePipeline(RuntimeError("429"))), 0.1)
    assert store.calls == [("requeue", "d1")]


async def test_gives_up_after_max_attempts():
    store = FakeStore([job(1, attempts=4)])
    pipeline = FakePipeline()
    await run_for(worker(store, pipeline, max_attempts=3), 0.1)
    assert store.calls == [("failed", "d1")]
    assert pipeline.done == []


async def test_cancel_mid_job_releases():
    store = FakeStore([job(1)])
    pipeline = FakePipeline(delay=10)
    task = asyncio.create_task(worker(store, pipeline).run_forever())
    await asyncio.wait_for(pipeline.started.wait(), 1)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert store.calls == [("release", "d1")]


async def test_claim_error_does_not_kill_loop():
    store = FakeStore([job(1)], claim_errors=2)
    pipeline = FakePipeline()
    await run_for(worker(store, pipeline), 0.1)
    assert pipeline.done == ["d1"]
