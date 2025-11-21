import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class Document(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")
    user_id: str
    name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True  # Allow both _id and id
        json_schema_extra = {
            "example": {
                "_id": "123",
                "name": "Test Document",
                "created_at": "2024-01-01T00:00:00",
            }
        }
