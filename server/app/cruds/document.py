import uuid
from datetime import datetime
from typing import List
from loguru import logger
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    document as model_document,
    user as model_user,
)


async def create_document(
    db: AsyncSession,
    current_user: model_user.User,
    files_in: List[str]
) -> List[model_document.Document]:
    """Create document records in PostgreSQL for the given filenames.

    Ensures uniqueness by document name for the current user. If a name already exists
    it will be skipped and reported in a warning. If none of the provided names
    can be inserted because they all exist, a ValueError is raised.
    Returns a list of created Document models.
    """
    created: List[model_document.Document] = []
    skipped: List[str] = []

    for name in files_in:
        file_name = name.split(".")[0]

        stmt = select(model_document.Document).where(
            model_document.Document.name == file_name,
            model_document.Document.user_id == current_user.id,
        )
        result = await db.execute(stmt)
        existing = result.scalars().first()
        if existing:
            skipped.append(name)
            continue

        doc = model_document.Document(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            name=file_name,
            created_at=datetime.utcnow(),
        )

        try:
            db.add(doc)
            await db.commit()
            await db.refresh(doc)
            created.append(doc)
        except IntegrityError:
            await db.rollback()
            skipped.append(name)

    if not created and skipped:
        raise ValueError(f"Document(s) already exist: {', '.join(skipped)}")

    if skipped:
        logger.warning(
            "Some documents were skipped because they already exist: {}", skipped
        )

    return created


async def delete_document(
    db: AsyncSession,
    current_user: model_user.User,
    document_id: str
) -> bool:
    """Delete a document from PostgreSQL."""
    stmt = delete(model_document.Document).where(
        model_document.Document.id == document_id,
        model_document.Document.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    await db.commit()
    return bool(result.rowcount and result.rowcount > 0)


async def get_documents(
    db: AsyncSession, current_user: model_user.User
) -> List[model_document.Document]:
    """Return all documents belonging to current_user from PostgreSQL."""
    stmt = select(model_document.Document).where(
        model_document.Document.user_id == current_user.id
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
