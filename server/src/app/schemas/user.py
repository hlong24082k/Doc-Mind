import uuid

from pydantic import BaseModel, Field
from datetime import datetime


# ------------------
# User schema
# ------------------

class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)


class UserResponse(UserBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# ------------------
# Login schema
# ------------------

class LoginResponse(BaseModel):
    access_token: str
    token_type: str