import uuid
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError
from loguru import logger

from src.app.security.security import get_password_hash
from src.app.models import (
    user as model_user,
)
from src.app.schemas import (
    user as schema_user
)

# =========================================================
# Query functions
# =========================================================

async def get_user_by_username(db: AsyncIOMotorDatabase, username: str) -> model_user.User | None:
    """Get user by username from MongoDB."""
    user_doc = await db["user"].find_one({"username": username})
    if user_doc:
        # Convert MongoDB document to User model
        # Handle _id field
        if "_id" in user_doc and "id" not in user_doc:
            user_doc["id"] = str(user_doc["_id"])
        return model_user.User(**user_doc)
    return None


# =========================================================
# Create function
# =========================================================

async def create_user(db: AsyncIOMotorDatabase, user_in: schema_user.UserCreate) -> model_user.User:
    """Create a new user in MongoDB."""
    hashed_password = get_password_hash(user_in.password)
    
    # Check if user already exists
    existing_user = await get_user_by_username(db, user_in.username)
    if existing_user:
        raise ValueError("User with this username already exists.")
    
    # Create user document
    user_doc = {
        "_id": str(uuid.uuid4()),
        "username": user_in.username,
        "hash_password": hashed_password,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    
    try:
        await db["user"].insert_one(user_doc)
        # Return user model
        user_doc["id"] = user_doc["_id"]
        return model_user.User(**user_doc)
    except DuplicateKeyError:
        raise ValueError("User with this username already exists.")
