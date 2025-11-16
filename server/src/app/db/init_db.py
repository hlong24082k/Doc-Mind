from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import logging

from src.app.db.session import get_db
from src.app.config import settings

logger = logging.getLogger(__name__)


# =========================================================
# Init database
# =========================================================
async def init_db_async():
    """Initialize MongoDB indexes asynchronously."""
    try:
        db = await get_db()
        
        # Create indexes for users collection
        # Unique index on username
        await db.users.create_index("username", unique=True)
        logger.info("Created unique index on users.username")
        
        # Index on _id is automatically created by MongoDB
        logger.info("MongoDB indexes initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize MongoDB indexes: {str(e)}")
        raise


def init_db():
    """Initialize MongoDB indexes (synchronous wrapper for async function)."""
    try:
        # Try to get the current event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is already running, we can't use run_until_complete
            # Create a task instead (but this won't wait for completion)
            logger.warning("Event loop is already running. Indexes will be created asynchronously.")
            asyncio.create_task(init_db_async())
        else:
            # If no loop is running, run it
            loop.run_until_complete(init_db_async())
    except RuntimeError:
        # If there's no event loop, create one
        asyncio.run(init_db_async())


if __name__ == "__main__":
    init_db()