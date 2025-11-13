
import uuid

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(255), unique=True, index= True, nullable=False)
    hash_password: Mapped[str] = mapped_column(String(255), nullable=False)
