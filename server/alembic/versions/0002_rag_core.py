"""rag core: extensions, documents columns, document_chunks, HNSW, BM25

Revision ID: 0002_rag_core
Revises: 0001_baseline
Create Date: 2026-10-12

"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002_rag_core"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_search")

    op.execute("""
        ALTER TABLE documents
          ADD COLUMN title        VARCHAR(512),
          ADD COLUMN status       VARCHAR(16) NOT NULL DEFAULT 'pending',
          ADD COLUMN content_hash CHAR(64),
          ADD COLUMN num_pages    INTEGER,
          ADD COLUMN num_chunks   INTEGER NOT NULL DEFAULT 0,
          ADD COLUMN error        TEXT,
          ADD COLUMN indexed_at   TIMESTAMP,
          ADD CONSTRAINT ck_documents_status
              CHECK (status IN ('pending', 'processing', 'indexed', 'failed'))
        """)

    op.execute("""
        CREATE TABLE document_chunks (
          id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          document_id   VARCHAR(36) NOT NULL
                        REFERENCES documents(id) ON DELETE CASCADE,
          user_id       VARCHAR(36) NOT NULL
                        REFERENCES users(id) ON DELETE CASCADE,
          chunk_index   INTEGER NOT NULL,
          section       TEXT,
          content       TEXT NOT NULL,
          overlap_chars INTEGER NOT NULL DEFAULT 0,
          page_start    INTEGER NOT NULL,
          page_end      INTEGER NOT NULL,
          token_count   INTEGER NOT NULL,
          embedding     vector(768) NOT NULL,
          created_at    TIMESTAMP NOT NULL DEFAULT now(),
          CONSTRAINT uq_document_chunks_document_id_chunk_index
              UNIQUE (document_id, chunk_index)
        )
        """)

    op.execute("""
        CREATE INDEX ix_document_chunks_user_id_document_id
          ON document_chunks (user_id, document_id)
        """)
    op.execute("""
        CREATE INDEX ix_document_chunks_embedding_hnsw
          ON document_chunks USING hnsw (embedding vector_cosine_ops)
          WITH (m = 16, ef_construction = 64)
        """)
    op.execute("""
        CREATE INDEX ix_document_chunks_bm25
          ON document_chunks
          USING paradedb (
            id,
            (content::pdb.simple('stemmer=english', 'stopwords_language=english')),
            (user_id::pdb.literal),
            (document_id::pdb.literal)
          )
          WITH (key_field = 'id')
        """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_bm25")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_user_id_document_id")
    op.execute("DROP TABLE IF EXISTS document_chunks")
    op.execute("""
        ALTER TABLE documents
          DROP CONSTRAINT IF EXISTS ck_documents_status,
          DROP COLUMN IF EXISTS indexed_at,
          DROP COLUMN IF EXISTS error,
          DROP COLUMN IF EXISTS num_chunks,
          DROP COLUMN IF EXISTS num_pages,
          DROP COLUMN IF EXISTS content_hash,
          DROP COLUMN IF EXISTS status,
          DROP COLUMN IF EXISTS title
        """)
