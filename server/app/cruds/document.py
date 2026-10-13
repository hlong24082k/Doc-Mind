import asyncio
import hashlib
import os
import uuid
from pathlib import Path

from loguru import logger
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from app.config import settings
from app.cruds import Conflict
from app.models.document import Document
from app.models.user import User
from app.schemas.document import Usage

CHUNK = 1 << 20
PDF_MAGIC = b"%PDF-"


class UploadRejected(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


async def usage(db: AsyncSession, user_id: str) -> Usage:
    used, count = (
        await db.execute(
            select(func.coalesce(func.sum(Document.size_bytes), 0), func.count()).where(
                Document.user_id == user_id
            )
        )
    ).one()
    return Usage(
        bytes=used,
        documents=count,
        quota_bytes=settings.user_quota_mb << 20,
        quota_documents=settings.user_quota_documents,
    )


async def list_documents(db: AsyncSession, user: User) -> list[Document]:
    return list(
        (
            await db.execute(
                select(Document)
                .where(Document.user_id == user.id)
                .order_by(Document.created_at.desc())
            )
        ).scalars()
    )


async def copy_to_tmp(file: UploadFile, user_dir: Path) -> tuple[Path, str, int]:
    """Copy file đã spool → user_dir/.tmp-{uuid}.pdf theo khối 1 MiB, tính
    sha256. 5 byte đầu != %PDF- → UploadRejected("not_pdf"), không tạo tmp."""
    await file.seek(0)
    head = await file.read(len(PDF_MAGIC))
    if head != PDF_MAGIC:
        raise UploadRejected("not_pdf")

    digest = hashlib.sha256()
    size = 0
    tmp = user_dir / f".tmp-{uuid.uuid4().hex}.pdf"
    out = await asyncio.to_thread(open, tmp, "wb")

    def sink(chunk: bytes) -> None:
        digest.update(chunk)
        out.write(chunk)

    try:
        chunk = head
        while chunk:
            await asyncio.to_thread(sink, chunk)
            size += len(chunk)
            chunk = await file.read(CHUNK)  # Starlette đã tự offload
    except BaseException:
        out.close()
        tmp.unlink(missing_ok=True)
        raise
    await asyncio.to_thread(out.close)
    return tmp, digest.hexdigest(), size


async def upsert_upload(
    db: AsyncSession,
    user: User,
    name: str,
    tmp: Path,
    content_hash: str,
    size: int,
) -> tuple[Document | None, str | None]:
    """Một transaction, khóa row user để tính quota tuần tự theo user.
    os.replace chạy TRƯỚC commit: worker dùng SKIP LOCKED nên không claim
    được row đang khóa, và khi thấy row thì file trên đĩa đã là bản mới.
    Mọi nhánh reject và mọi exception đều xóa tmp."""
    try:
        await db.execute(
            text("SELECT 1 FROM users WHERE id = :uid FOR UPDATE"),
            {"uid": user.id},
        )
        existing = (
            (
                await db.execute(
                    select(Document)
                    .where(
                        Document.user_id == user.id,
                        func.lower(Document.name) == func.lower(name),
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .first()
        )
        used = await usage(db, user.id)
        new_bytes = used.bytes - (existing.size_bytes if existing else 0) + size
        new_docs = used.documents + (0 if existing else 1)

        reason = None
        if new_bytes > used.quota_bytes or new_docs > used.quota_documents:
            reason = "quota_exceeded"
        elif existing and existing.status == "processing":
            reason = "busy"
        elif (
            existing
            and existing.content_hash == content_hash
            and existing.status in ("pending", "indexed")
        ):
            reason = "unchanged"
        if reason:
            await db.rollback()
            tmp.unlink(missing_ok=True)
            return None, reason

        if existing is None:
            doc = Document(
                user_id=user.id,
                name=name,
                status="pending",
                content_hash=content_hash,
                size_bytes=size,
            )
            db.add(doc)
            await db.flush()
        else:  # giữ nguyên existing.name (cách viết hoa/thường cũ)
            doc = existing
            doc.status = "pending"
            doc.content_hash = content_hash
            doc.size_bytes = size
            doc.attempts = 0
            doc.error = None
            doc.claimed_at = None
        await asyncio.to_thread(
            os.replace, tmp, settings.document_file_path(user.id, doc.name)
        )
        await db.commit()
        return doc, None
    except BaseException:
        await db.rollback()
        tmp.unlink(missing_ok=True)
        raise


async def get_owned(db: AsyncSession, user: User, document_id: str) -> Document | None:
    return (
        (
            await db.execute(
                select(Document).where(
                    Document.id == document_id, Document.user_id == user.id
                )
            )
        )
        .scalars()
        .first()
    )


async def delete_owned(db: AsyncSession, user: User, document_id: str) -> bool:
    """Xóa row (chunk bị cascade) rồi xóa file."""
    name = (
        await db.execute(
            delete(Document)
            .where(Document.id == document_id, Document.user_id == user.id)
            .returning(Document.name)
        )
    ).scalar_one_or_none()
    await db.commit()
    if name is None:
        return False
    try:
        path = settings.document_file_path(user.id, name)
        await asyncio.to_thread(path.unlink, missing_ok=True)
    except (OSError, ValueError):
        logger.exception("cannot delete file of document {}", document_id)
    return True


async def requeue_owned(
    db: AsyncSession, user: User, document_id: str
) -> Document | None:
    """Đưa về pending, attempts=0. Raise Conflict nếu đang processing."""
    doc = (
        (
            await db.execute(
                select(Document)
                .where(Document.id == document_id, Document.user_id == user.id)
                .with_for_update()
            )
        )
        .scalars()
        .first()
    )
    if doc is None:
        await db.rollback()
        return None
    if doc.status == "processing":
        await db.rollback()
        raise Conflict("Document is processing")
    await db.execute(
        update(Document)
        .where(Document.id == doc.id)
        .values(status="pending", attempts=0, error=None, claimed_at=None)
    )
    await db.commit()
    await db.refresh(doc)
    return doc
