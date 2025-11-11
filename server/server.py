import uvicorn

from src.app.config import settings


if __name__ == "__main__":
    uvicorn.run(
        "src.app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=1,                # increase for production (e.g., 4)
        log_level="info" 
    )
