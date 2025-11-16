import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class User(BaseModel):
    """User model for MongoDB."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")
    username: str
    hash_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True  # Allow both _id and id
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "username": "johndoe",
                "hash_password": "hashed_password_here",
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00"
            }
        }
