from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from src.app.db.session import connect_and_init_db, close_db_connect
from src.app.routers import api_router
from src.app.config import settings


app = FastAPI(
    title=settings.name,
    version=settings.version,
    description=settings.description
)

app.add_event_handler("startup", connect_and_init_db)
app.add_event_handler("shutdown", close_db_connect)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
