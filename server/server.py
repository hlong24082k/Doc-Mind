import uvicorn

from src.app.config import settings


if __name__ == "__main__":
    uvicorn.run(
        "src.app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info" 
    )
