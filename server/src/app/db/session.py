import asyncio
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorClient

from src.app.config import settings



db_client: AsyncIOMotorClient = None
db_uri: str = settings.db_uri


async def get_db() -> AsyncIOMotorClient:
    db_name = settings.mongo_db
    return db_client[db_name]


async def connect_and_init_db():
    global db_client
    try:
        db_client = AsyncIOMotorClient(
            db_uri,
        )
        logger.info(f'Connected to mongo: {db_uri}')
    except Exception as e:
        logger.debug(f'Could not connect to mongo: {e}')
        raise


async def close_db_connect():
    global db_client
    if db_client is None:
        logger.debug('Connection is None, nothing to close.')
        return
    db_client.close()
    db_client = None
    logger.info('Mongo connection closed.')
