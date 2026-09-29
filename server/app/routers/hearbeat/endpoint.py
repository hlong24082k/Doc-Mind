from fastapi import APIRouter


heartbeat_router = APIRouter()


@heartbeat_router.get("/health")
async def health_check():
    return {"status": "ok"}
