"""Embeddings from the local Ollama server (spec Section 3, ADR-0005: bge-m3, 1024 dimensions).

Texts go to `POST {OLLAMA_URL}/api/embed` in batches. bge-m3 needs no query or passage prefix, so
`embed_query` and `embed_documents` differ only in intent. Texts are never logged
(docs/conventions.md, Logging and privacy): only the model, counts and timing.
"""

import logging
import time
from collections.abc import Sequence

import httpx

from app.config import Settings

logger = logging.getLogger("insighthub.embeddings")

EMBEDDING_DIMENSION = 1024  # fixed by the chunks table's vector(1024) (ADR-0005)


class EmbeddingError(RuntimeError):
    """The embedding server failed or returned something unusable."""


class OllamaEmbedder:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout: float = 60.0,
        batch_size: int = 16,
        client: httpx.Client | None = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self._model = model
        self._batch_size = batch_size
        self._client = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)

    @classmethod
    def from_settings(cls, settings: Settings) -> "OllamaEmbedder":
        if not settings.embedding_model:
            raise EmbeddingError("EMBEDDING_MODEL is not set")
        return cls(
            settings.ollama_url,
            settings.embedding_model,
            timeout=settings.embedding_timeout_seconds,
            batch_size=settings.embedding_batch_size,
        )

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """One vector per text, in order. An empty input returns an empty list."""
        started = time.monotonic()
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            vectors.extend(self._embed_batch(list(texts[start : start + self._batch_size])))
        logger.info(
            "embedded model=%s texts=%d seconds=%.2f",
            self._model,
            len(texts),
            time.monotonic() - started,
        )
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        try:
            response = self._client.post("/api/embed", json={"model": self._model, "input": batch})
            response.raise_for_status()
            embeddings = response.json()["embeddings"]
        except httpx.HTTPError as error:
            # Class and status only: the message could echo request content.
            raise EmbeddingError(f"embedding request failed: {type(error).__name__}") from None
        except (ValueError, KeyError, TypeError):
            raise EmbeddingError("embedding response was not the expected JSON") from None

        if len(embeddings) != len(batch):
            raise EmbeddingError(f"expected {len(batch)} vectors, got {len(embeddings)}")
        for vector in embeddings:
            if len(vector) != EMBEDDING_DIMENSION:
                raise EmbeddingError(
                    f"expected {EMBEDDING_DIMENSION} dimensions, got {len(vector)}; "
                    "is EMBEDDING_MODEL still bge-m3?"
                )
        return embeddings
