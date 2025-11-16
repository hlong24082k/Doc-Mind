# src/app/db/base.py

from sqlalchemy.orm import declarative_base
from sqlalchemy import MetaData
import logging

logger = logging.getLogger(__name__)

# =========================================================
# Metadata
# =========================================================

metadata = MetaData(
    naming_convention={
        "pk": "pk_%(table_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
    },
)


# =========================================================
# Declarative
# =========================================================

# Base = declarative_base(metadata=metadata)
Base = declarative_base()
logger.info("SQLAlchemy Declarative Base initialized with utf8mb4 metadata.")
