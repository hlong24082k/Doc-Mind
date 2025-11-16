from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import APIRouter, status, Depends, HTTPException

from src.app.db.session import get_db
from src.app.schemas import (
    user as schema_user
)
from src.app.cruds import user as crud_user

auth_router = APIRouter()


@auth_router.post(
    "/register",
    response_model=schema_user.UserResponse,
    status_code=status.HTTP_201_CREATED
)
async def register_user(
    user_in: schema_user.UserCreate,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if await crud_user.get_user_by_username(db, user_in.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Username already taken."
        )
    user = await crud_user.create_user(db, user_in)
    return user
