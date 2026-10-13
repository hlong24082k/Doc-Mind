from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.config import settings
from app.cruds import user as crud_user
from app.db.session import AsyncSessionLocal
from app.models import user as model_user

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
) -> model_user.User:
    """Tự mở session ngắn (không dùng get_db) để route SSE không giữ
    connection suốt thời gian stream."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    async with AsyncSessionLocal() as db:
        user = await crud_user.get_user_by_username(db=db, username=username)
    if user is None:
        raise credentials_exception

    return user
