import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.factory import build_api_services, build_ingest_worker
from app.db.session import close_db_connect, connect_and_init_db
from app.routers import api_router
from app.routers.conversation.limiter import ChatLimiter
from app.routers.document.limits import UploadLimiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await connect_and_init_db()
    settings.documents_folder_path.mkdir(parents=True, exist_ok=True)
    app.state.upload_limiter = UploadLimiter(settings.upload_max_concurrency)
    app.state.chat_limiter = ChatLimiter(
        settings.chat_max_concurrency, settings.chat_queue_timeout_s
    )
    app.state.services = build_api_services()
    worker = None
    if settings.ingest_worker_enabled:
        worker = asyncio.create_task(build_ingest_worker().run_forever())
    yield
    # Shutdown: hủy worker → job đang dở được release về pending
    if worker is not None:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker
    await close_db_connect()


app = FastAPI(
    title=settings.name,
    version=settings.version,
    description=settings.description,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
