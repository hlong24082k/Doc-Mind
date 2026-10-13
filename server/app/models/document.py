import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Document(Base):
    """Document model for PostgreSQL."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'indexed', 'failed')",
            name="status",
        ),
        # unique không phân biệt hoa/thường: APFS coi Paper.pdf == paper.pdf
        Index(
            "uq_documents_user_id_lower_name",
            "user_id",
            func.lower(text("name")),
            unique=True,
        ),
        # index cho câu claim của worker (chỉ chứa job chưa xong)
        Index(
            "ix_documents_queue",
            "created_at",
            postgresql_where=text("status IN ('pending', 'processing')"),
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    content_hash: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    num_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_chunks: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    size_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )

    @property
    def _id(self) -> str:
        return self.id

    def to_dict(self) -> dict:
        return {
            "_id": self.id,
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "title": self.title,
            "status": self.status,
            "error": self.error,
            "size_bytes": self.size_bytes,
            "num_pages": self.num_pages,
            "num_chunks": self.num_chunks,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "indexed_at": self.indexed_at.isoformat() if self.indexed_at else None,
        }

    def dict(self, *args, **kwargs) -> dict:
        return self.to_dict()
