"""Reads and writes of the chunks table (docs/conventions.md, Vector DB).

Plain SQL through SQLAlchemy Core: the embedding goes in as a pgvector text literal, so no extra
package is needed. Every search takes a Scope and filters only through `where_clause(scope_filter(...))`
(CLAUDE.md hard rule 1). Chunk text is never logged.
"""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, text

from app.api.scope import CourseScope, IngestScope, PersonalScope
from app.clients.embeddings import EMBEDDING_DIMENSION
from app.ingestion.chunking import Chunk
from app.rag.scope_filter import scope_filter, where_clause

logger = logging.getLogger("insighthub.repository")

_INSERT = text(
    """
    INSERT INTO chunks (
        document_id, chunk_index, scope_type, classroom_id, course_id, workspace_id, owner_id,
        text, source_type, file_name, source_url, page, slide, section_path,
        start_seconds, end_seconds, language, version, retrieved_at, embedding
    ) VALUES (
        :document_id, :chunk_index, :scope_type, :classroom_id, :course_id, :workspace_id, :owner_id,
        :text, :source_type, :file_name, :source_url, :page, :slide, CAST(:section_path AS text[]),
        :start_seconds, :end_seconds, :language, :version, :retrieved_at, CAST(:embedding AS vector)
    )
    """
)


class ChunkHit(BaseModel):
    """One search result, with what a citation needs."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    document_id: UUID
    text: str
    score: float  # cosine similarity, higher is closer
    source_type: str
    file_name: str | None
    source_url: str | None
    page: int | None
    slide: int | None
    section_path: tuple[str, ...]
    start_seconds: float | None
    end_seconds: float | None


def _vector_literal(vector: Sequence[float]) -> str:
    if len(vector) != EMBEDDING_DIMENSION:
        raise ValueError(f"expected {EMBEDDING_DIMENSION} dimensions, got {len(vector)}")
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def _scope_columns(scope: IngestScope) -> dict[str, Any]:
    if scope.scope_type == "personal":
        return {
            "scope_type": "personal",
            "classroom_id": None,
            "course_id": None,
            "workspace_id": scope.workspace_id,
            "owner_id": scope.owner_id,
        }
    return {
        "scope_type": "course",
        "classroom_id": scope.classroom_id,
        "course_id": scope.course_id,
        "workspace_id": None,
        "owner_id": None,
    }


class ChunkRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def replace_document(
        self,
        *,
        document_id: UUID,
        scope: IngestScope,
        chunks: Sequence[Chunk],
        embeddings: Sequence[Sequence[float]],
        file_name: str | None = None,
        source_url: str | None = None,
        language: str | None = None,
    ) -> int:
        """Store the document's chunks in place of any earlier ones and return the new version.

        One transaction: readers see the old chunks until it commits and the new ones after, never a
        mix, and a failure leaves the old chunks untouched. The first ingest is version 1.
        """
        if len(chunks) != len(embeddings):
            raise ValueError(f"{len(chunks)} chunks but {len(embeddings)} embeddings")
        vectors = [
            _vector_literal(embedding) for embedding in embeddings
        ]  # validates before any write

        with self._engine.begin() as connection:
            # Serialises concurrent ingests of the same document for the length of the transaction.
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:document_id))"),
                {"document_id": str(document_id)},
            )
            previous = connection.execute(
                text("SELECT max(version) FROM chunks WHERE document_id = :document_id"),
                {"document_id": document_id},
            ).scalar()
            version = (previous or 0) + 1
            connection.execute(
                text("DELETE FROM chunks WHERE document_id = :document_id"),
                {"document_id": document_id},
            )
            if chunks:
                retrieved_at = datetime.now(UTC) if source_url else None
                connection.execute(
                    _INSERT,
                    [
                        {
                            "document_id": document_id,
                            "chunk_index": chunk.index,
                            **_scope_columns(scope),
                            "text": chunk.text,
                            "source_type": chunk.source_type,
                            "file_name": file_name,
                            "source_url": source_url,
                            "page": chunk.anchor.page,
                            "slide": chunk.anchor.slide,
                            "section_path": list(chunk.anchor.section_path),
                            "start_seconds": chunk.anchor.start_seconds,
                            "end_seconds": chunk.anchor.end_seconds,
                            "language": language,
                            "version": version,
                            "retrieved_at": retrieved_at,
                            "embedding": vector,
                        }
                        for chunk, vector in zip(chunks, vectors, strict=True)
                    ],
                )
        logger.info("replaced document=%s chunks=%d version=%d", document_id, len(chunks), version)
        return version

    def search_chunks(
        self, scope: PersonalScope | CourseScope, embedding: Sequence[float], limit: int = 10
    ) -> list[ChunkHit]:
        """The closest chunks inside the scope, nearest first. Nothing outside it is ever returned."""
        if limit < 1:
            raise ValueError("limit must be at least 1")
        condition, params = where_clause(scope_filter(scope))
        query = text(
            f"""
            SELECT id, document_id, text, 1 - (embedding <=> CAST(:query AS vector)) AS score,
                   source_type, file_name, source_url, page, slide, section_path,
                   start_seconds, end_seconds
            FROM chunks
            WHERE {condition}
            ORDER BY embedding <=> CAST(:query AS vector)
            LIMIT :limit
            """
        )
        with self._engine.begin() as connection:
            # Keep recall when the scope filter removes most of the index's candidates (pgvector 0.8+).
            connection.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
            rows = connection.execute(
                query, {**params, "query": _vector_literal(embedding), "limit": limit}
            ).mappings()
            return [ChunkHit(**{**row, "section_path": tuple(row["section_path"])}) for row in rows]

    def delete_document(self, document_id: UUID) -> int:
        """Remove one document's chunks. Idempotent: an unknown document deletes nothing."""
        return self._delete("document_id = :id", document_id)

    def delete_workspace(self, workspace_id: UUID) -> int:
        """Remove the personal sources of a workspace. Course chunks are never held per workspace."""
        return self._delete("scope_type = 'personal' AND workspace_id = :id", workspace_id)

    def delete_owner(self, owner_id: UUID) -> int:
        """Remove the personal sources of a user (account deletion)."""
        return self._delete("scope_type = 'personal' AND owner_id = :id", owner_id)

    def list_document_ids(
        self,
        *,
        scope_type: Literal["personal", "course"] | None = None,
        limit: int = 1000,
        after: UUID | None = None,
    ) -> list[UUID]:
        """Document ids in id order, for the backend's reconciliation. Pass the last id as `after`."""
        if limit < 1:
            raise ValueError("limit must be at least 1")
        conditions = ["TRUE"]
        params: dict[str, Any] = {"limit": limit}
        if scope_type is not None:
            conditions.append("scope_type = :scope_type")
            params["scope_type"] = scope_type
        if after is not None:
            conditions.append("document_id > :after")
            params["after"] = after
        query = text(
            f"SELECT DISTINCT document_id FROM chunks WHERE {' AND '.join(conditions)} "
            "ORDER BY document_id LIMIT :limit"
        )
        with self._engine.connect() as connection:
            return [row[0] for row in connection.execute(query, params)]

    def _delete(self, condition: str, value: UUID) -> int:
        with self._engine.begin() as connection:
            deleted = connection.execute(
                text(f"DELETE FROM chunks WHERE {condition}"),
                {"id": value},
            ).rowcount
        logger.info("deleted rows=%d", deleted)
        return deleted
