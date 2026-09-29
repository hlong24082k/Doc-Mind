import uuid
from datetime import datetime
from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import user as model_user
from app.schemas import user as schema_user
from app.security.security import get_password_hash

# =========================================================
# Query functions
# =========================================================


async def get_user_by_username(
    db: AsyncSession, username: str
) -> model_user.User | None:
    """Get user by username from PostgreSQL."""
    stmt = select(model_user.User).where(model_user.User.username == username)
    result = await db.execute(stmt)
    return result.scalars().first()


# =========================================================
# Create function
# =========================================================


async def create_user(
    db: AsyncSession, user_in: schema_user.UserCreate
) -> model_user.User:
    """Create a new user in PostgreSQL."""
    # Check if user already exists
    existing_user = await get_user_by_username(db, user_in.username)
    if existing_user:
        raise ValueError("User with this username already exists.")

    hashed_password = get_password_hash(user_in.password)
    user = model_user.User(
        id=str(uuid.uuid4()),
        username=user_in.username,
        hash_password=hashed_password,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    try:
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user
    except IntegrityError:
        await db.rollback()
        raise ValueError("User with this username already exists.")
