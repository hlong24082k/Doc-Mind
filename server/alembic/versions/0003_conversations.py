"""conversations: queue columns, case-insensitive name, conversations, messages

Revision ID: 0003_conversations
Revises: 0002_rag_core
Create Date: 2026-10-13

"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003_conversations"
down_revision: Union[str, None] = "0002_rag_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE documents
          ADD COLUMN attempts   INTEGER NOT NULL DEFAULT 0,
          ADD COLUMN claimed_at TIMESTAMP,
          ADD COLUMN size_bytes BIGINT  NOT NULL DEFAULT 0
        """)

    # unique không phân biệt hoa/thường: macOS (APFS) coi Paper.pdf và
    # paper.pdf là cùng một file, nên DB cũng phải coi đó là cùng một document
    op.execute("""
        CREATE UNIQUE INDEX uq_documents_user_id_lower_name
          ON documents (user_id, lower(name))
        """)

    # index cho câu claim của worker (chỉ chứa job chưa xong → rất nhỏ)
    op.execute("""
        CREATE INDEX ix_documents_queue ON documents (created_at)
          WHERE status IN ('pending', 'processing')
        """)

    op.execute("""
        CREATE TABLE conversations (
          id           VARCHAR(36) PRIMARY KEY,
          user_id      VARCHAR(36) NOT NULL
                       REFERENCES users(id) ON DELETE CASCADE,
          title        VARCHAR(255),
          document_ids VARCHAR(36)[] NOT NULL,
          created_at   TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
          updated_at   TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
          CONSTRAINT ck_conversations_document_ids
              CHECK (cardinality(document_ids) BETWEEN 1 AND 10)
        )
        """)
    op.execute("""
        CREATE INDEX ix_conversations_user_id_updated_at
          ON conversations (user_id, updated_at DESC)
        """)

    op.execute("""
        CREATE TABLE messages (
          id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          conversation_id  VARCHAR(36) NOT NULL
                           REFERENCES conversations(id) ON DELETE CASCADE,
          role             VARCHAR(16) NOT NULL,
          content          TEXT NOT NULL,
          standalone_query TEXT,
          sources          JSONB,
          grounded         BOOLEAN,
          refused          BOOLEAN,
          timings_ms       JSONB,
          created_at       TIMESTAMP NOT NULL
                           DEFAULT (now() AT TIME ZONE 'utc'),
          CONSTRAINT ck_messages_role CHECK (role IN ('user', 'assistant'))
        )
        """)
    op.execute("""
        CREATE INDEX ix_messages_conversation_id_id
          ON messages (conversation_id, id)
        """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_messages_conversation_id_id")
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP INDEX IF EXISTS ix_conversations_user_id_updated_at")
    op.execute("DROP TABLE IF EXISTS conversations")
    op.execute("DROP INDEX IF EXISTS ix_documents_queue")
    op.execute("DROP INDEX IF EXISTS uq_documents_user_id_lower_name")
    op.execute("""
        ALTER TABLE documents
          DROP COLUMN IF EXISTS size_bytes,
          DROP COLUMN IF EXISTS claimed_at,
          DROP COLUMN IF EXISTS attempts
        """)
