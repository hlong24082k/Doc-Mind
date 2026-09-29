from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.session import close_db_connect, connect_and_init_db
from app.routers import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await connect_and_init_db()
    yield
    # Shutdown
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
