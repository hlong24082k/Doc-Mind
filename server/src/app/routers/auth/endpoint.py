from datetime import timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import APIRouter, status, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm

from src.app.db.session import get_db
from src.app.schemas import (
    user as schema_user
)
from src.app.cruds import (
    user as crud_user
)
from src.app.security.security import verify_password, create_access_token
from src.app.config import settings


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


@auth_router.post(
    "/login", 
    status_code=status.HTTP_200_OK,
    response_model=schema_user.LoginResponse
)
async def login(
    db: AsyncIOMotorDatabase = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
):
    user = await crud_user.get_user_by_username(db, username=form_data.username)
    is_verified_password = verify_password(
        plain_password=form_data.password,
        hashed_password=user.hash_password
    )
    if not user or not is_verified_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.jwt_access_token_expire_minutes)
    access_token = create_access_token(
        subject=user.username, expires_delta=access_token_expires
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=schema_user.LoginResponse(
            access_token=access_token,
            token_type="bearer"
        ).model_dump()
    )
