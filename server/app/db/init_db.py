import asyncio
from loguru import logger
from sqlalchemy import select

from app.db.base import Base
from app.db.session import engine, AsyncSessionLocal
# Import models to ensure they are registered with Base.metadata
from app.models.user import User
from app.models.document import Document
from app.security.security import get_password_hash
from app.config import settings


async def init_db_async():
    """Initialize PostgreSQL database tables and seed default superuser."""
    try:
        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("PostgreSQL tables checked/created successfully.")

        # Seed superuser
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.username == settings.first_superuser)
            result = await session.execute(stmt)
            existing_user = result.scalars().first()

            if not existing_user:
                logger.info(f"Seeding default superuser: '{settings.first_superuser}'")
                hashed_pw = get_password_hash(settings.first_superuser_password)
                super_user = User(
                    username=settings.first_superuser,
                    hash_password=hashed_pw,
                )
                session.add(super_user)
                await session.commit()
                logger.info(
                    f"Default user '{settings.first_superuser}' created successfully."
                )
            else:
                logger.info(
                    f"Superuser '{settings.first_superuser}' already exists in database."
                )
    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL: {str(e)}")
        raise


def init_db():
    """Synchronous wrapper for init_db_async."""
    asyncio.run(init_db_async())


if __name__ == "__main__":
    init_db()