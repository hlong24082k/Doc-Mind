from fastapi import APIRouter

from src.app.routers.hearbeat.endpoint import heartbeat_router

api_router = APIRouter()
api_router.include_router(heartbeat_router, prefix="/heartbeat", tags=["heartbeat"])
