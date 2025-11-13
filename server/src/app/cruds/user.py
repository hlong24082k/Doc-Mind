
from sqlalchemy.orm import Session

from src.app.models import (
    user as model_user,
)


def get_user_by_username(db: Session, username: str) -> model_user.User | None:
    return (
        db.query(model_user.User)
        .filter(model_user.User.username == username)
        .first()
    )