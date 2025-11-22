import uuid
from datetime import datetime
from typing import List
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError
from loguru import logger

from src.app.models import (
    document as model_document,
    user as model_user,
)

async def create_document(
    db: AsyncIOMotorDatabase,
    current_user: model_user.User,
    files_in: List[str]
) -> List[model_document.Document]:
    """Create document records in the database for the given filenames.

    Ensures uniqueness by document `name`. If a name already exists in the
    collection it will be skipped and reported in a warning. If none of the
    provided names can be inserted because they all exist, a ValueError is raised.
    Returns a list of created `Document` models.
    """
    created: List[model_document.Document] = []
    skipped: List[str] = []

    for name in files_in:
        # check existing by name to enforce uniqueness (no unique index required)
        file_name = name.split(".")[0]
        existing = await db["document"].find_one({"name": file_name})
        if existing:
            skipped.append(name)
            continue

        doc = model_document.Document(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            name=file_name,
            created_at=datetime.utcnow()
        )

        try:
            # Insert as dict, not Pydantic model
            await db["document"].insert_one(doc.dict(by_alias=True))
            created.append(doc)
        except DuplicateKeyError:
            # In case a unique index exists on name and a race condition occurs
            skipped.append(name)

    if not created and skipped:
        raise ValueError(f"Document(s) already exist: {', '.join(skipped)}")

    if skipped:
        logger.warning("Some documents were skipped because they already exist: {}", skipped)

    return created


async def delete_document(
    db: AsyncIOMotorDatabase,
    current_user: model_user.User,
    document_id: str
) -> bool:
    """Delete a document from the database."""
    result = await db["document"].delete_one({"_id": document_id, "user_id": current_user.id})
    return result.deleted_count > 0


async def get_documents(db: AsyncIOMotorDatabase, current_user: model_user.User) -> List[model_document.Document]:
    """Return all documents from the `document` collection as Pydantic models."""
    docs: List[model_document.Document] = []
    cursor = db["document"].find({"user_id": current_user.id})
    async for d in cursor:
        # Normalize Mongo `_id` to `id` if necessary
        if "_id" in d and "id" not in d:
            d["id"] = str(d["_id"])
            del d["_id"]
        docs.append(model_document.Document(**d))
    return docs
