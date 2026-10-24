"""create chunks table

Revision ID: b0af58135c79
Revises:
Create Date: 2026-10-24 16:06:00

Chunks with scope columns (spec Section 5), a 1024-dim bge-m3 embedding (ADR-0005) and a keyword
index. `document_id` is a plain UUID, no foreign key (ADR-0002).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b0af58135c79"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCOPE_COLUMNS = (
    "scope_type",
    "classroom_id",
    "course_id",
    "workspace_id",
    "owner_id",
    "document_id",
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE chunks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id uuid NOT NULL,
            chunk_index integer NOT NULL CHECK (chunk_index >= 0),
            scope_type text NOT NULL CHECK (scope_type IN ('course', 'personal')),
            classroom_id uuid,
            course_id uuid,
            workspace_id uuid,
            owner_id uuid,
            text text NOT NULL,
            source_type text NOT NULL,
            file_name text,
            source_url text,
            page integer,
            slide integer,
            section_path text[] NOT NULL DEFAULT '{}',
            start_seconds double precision,
            end_seconds double precision,
            language text,
            version integer NOT NULL DEFAULT 1,
            retrieved_at timestamptz,
            embedding vector(1024) NOT NULL,
            tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (document_id, chunk_index),
            CONSTRAINT chunks_scope_columns CHECK (
                (scope_type = 'course'
                    AND classroom_id IS NOT NULL AND course_id IS NOT NULL
                    AND workspace_id IS NULL AND owner_id IS NULL)
                OR
                (scope_type = 'personal'
                    AND workspace_id IS NOT NULL AND owner_id IS NOT NULL
                    AND classroom_id IS NULL AND course_id IS NULL)
            )
        )
        """
    )
    for column in SCOPE_COLUMNS:
        op.execute(f"CREATE INDEX chunks_{column}_idx ON chunks ({column})")
    op.execute("CREATE INDEX chunks_tsv_idx ON chunks USING gin (tsv)")
    op.execute(
        "CREATE INDEX chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE chunks")
    # The vector extension is left installed: other objects may use it.
