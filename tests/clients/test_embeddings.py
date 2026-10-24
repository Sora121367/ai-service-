import json

import httpx
import pytest

from app.clients.embeddings import EMBEDDING_DIMENSION, EmbeddingError, OllamaEmbedder
from app.config import Settings
from tests.conftest import settings_values


def _embedder(handler, batch_size: int = 16) -> OllamaEmbedder:
    client = httpx.Client(base_url="http://ollama:11434", transport=httpx.MockTransport(handler))
    return OllamaEmbedder("http://ollama:11434", "bge-m3", batch_size=batch_size, client=client)


def _vector(value: float = 0.1) -> list[float]:
    return [value] * EMBEDDING_DIMENSION


def test_embed_documents_returns_one_vector_per_text_in_order():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embed"
        body = json.loads(request.content)
        assert body["model"] == "bge-m3"
        return httpx.Response(200, json={"embeddings": [_vector(len(t)) for t in body["input"]]})

    vectors = _embedder(handler).embed_documents(["a", "bb", "ccc"])

    assert [v[0] for v in vectors] == [1, 2, 3]


def test_embed_documents_splits_into_batches():
    sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        texts = json.loads(request.content)["input"]
        sizes.append(len(texts))
        return httpx.Response(200, json={"embeddings": [_vector() for _ in texts]})

    vectors = _embedder(handler, batch_size=2).embed_documents(["a", "b", "c", "d", "e"])

    assert sizes == [2, 2, 1]
    assert len(vectors) == 5


def test_empty_input_makes_no_request():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    assert _embedder(handler).embed_documents([]) == []


def test_embed_query_returns_a_single_vector():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [_vector(0.5)]})

    assert _embedder(handler).embed_query("what is rag?") == _vector(0.5)


def test_wrong_dimension_is_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2]]})

    with pytest.raises(EmbeddingError, match="1024 dimensions"):
        _embedder(handler).embed_query("x")


def test_wrong_vector_count_is_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [_vector()]})

    with pytest.raises(EmbeddingError, match="expected 2 vectors"):
        _embedder(handler).embed_documents(["a", "b"])


def test_http_error_hides_the_request_text():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="secret student essay")

    with pytest.raises(EmbeddingError) as error:
        _embedder(handler).embed_query("secret student essay")

    assert "secret" not in str(error.value)


def test_unexpected_json_is_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"oops": 1})

    with pytest.raises(EmbeddingError, match="expected JSON"):
        _embedder(handler).embed_query("x")


def test_texts_are_not_logged(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [_vector()]})

    with caplog.at_level("INFO", logger="insighthub.embeddings"):
        _embedder(handler).embed_query("private chunk text")

    assert "private chunk text" not in caplog.text
    assert "model=bge-m3" in caplog.text


def test_from_settings_requires_a_model():
    settings = Settings(_env_file=None, **settings_values())

    with pytest.raises(EmbeddingError, match="EMBEDDING_MODEL"):
        OllamaEmbedder.from_settings(settings)


def test_from_settings_uses_configured_values():
    settings = Settings(_env_file=None, **settings_values(embedding_model="bge-m3"))

    assert isinstance(OllamaEmbedder.from_settings(settings), OllamaEmbedder)
