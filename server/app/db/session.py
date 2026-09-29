from typing import AsyncGenerator
from loguru import logger
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

engine: AsyncEngine = create_async_engine(
    settings.db_uri,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()


async def connect_and_init_db():
    from app.db.init_db import init_db_async

    try:
        logger.info("Initializing PostgreSQL database and models...")
        await init_db_async()
        logger.info("PostgreSQL database connected and initialized.")
    except Exception as e:
        logger.error(f"Could not connect to PostgreSQL: {e}")
        raise


async def close_db_connect():
    global engine
    if engine is not None:
        await engine.dispose()
        logger.info("PostgreSQL connection pool closed.")
