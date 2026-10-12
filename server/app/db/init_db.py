import asyncio
from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError

from app.db.session import engine, AsyncSessionLocal
# Import models to ensure they are registered with Base.metadata
from app.models.user import User
from app.models.document import Document
from app.security.security import get_password_hash
from app.config import settings


async def init_db_async():
    """Check migration state and seed default superuser."""
    try:
        # Schema được quản lý bởi Alembic, chỉ kiểm tra đã migrate chưa
        try:
            async with engine.connect() as conn:
                await conn.execute(
                    text("SELECT version_num FROM alembic_version")
                )
        except ProgrammingError:
            raise RuntimeError(
                "Database chưa được migrate. "
                "Chạy: uv run alembic upgrade head"
            )

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