from fastapi import APIRouter

from src.app.routers.hearbeat.endpoint import heartbeat_router
from src.app.routers.auth.endpoint import auth_router
from src.app.routers.document.endpoint import document_router

api_router = APIRouter()
api_router.include_router(heartbeat_router, prefix="/heartbeat", tags=["heartbeat"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(document_router, prefix="/document", tags=["document"])
