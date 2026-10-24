import io

import boto3
import pytest
from botocore.client import Config
from botocore.exceptions import EndpointConnectionError
from botocore.response import StreamingBody
from botocore.stub import Stubber

from app.clients.storage import ObjectNotFound, ObjectStorage, ObjectTooLarge, StorageError
from app.config import Settings
from tests.conftest import settings_values

BUCKET = "test-bucket"


@pytest.fixture
def s3():
    client = boto3.client(
        "s3",
        endpoint_url="http://s3:9000",
        aws_access_key_id="x",
        aws_secret_access_key="x",
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}),
    )
    with Stubber(client) as stubber:
        yield client, stubber


def _body(data: bytes) -> StreamingBody:
    return StreamingBody(io.BytesIO(data), len(data))


def _storage(client, max_bytes: int = 100) -> ObjectStorage:
    return ObjectStorage(client, BUCKET, max_bytes=max_bytes)


def test_get_bytes_returns_the_content(s3):
    client, stubber = s3
    stubber.add_response(
        "get_object",
        {"Body": _body(b"hello"), "ContentLength": 5},
        {"Bucket": BUCKET, "Key": "docs/a.pdf"},
    )

    assert _storage(client).get_bytes("docs/a.pdf") == b"hello"


def test_get_bytes_missing_object_raises_not_found(s3):
    client, stubber = s3
    stubber.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)

    with pytest.raises(ObjectNotFound):
        _storage(client).get_bytes("docs/missing.pdf")


def test_get_bytes_rejects_large_objects_by_declared_length(s3):
    client, stubber = s3
    stubber.add_response("get_object", {"Body": _body(b"x" * 10), "ContentLength": 10})

    with pytest.raises(ObjectTooLarge):
        _storage(client, max_bytes=5).get_bytes("docs/big.bin")


def test_get_bytes_rejects_large_objects_when_length_is_unknown(s3):
    client, stubber = s3
    stubber.add_response("get_object", {"Body": _body(b"x" * 10)})

    with pytest.raises(ObjectTooLarge):
        _storage(client, max_bytes=5).get_bytes("docs/big.bin")


def test_get_bytes_accepts_an_object_exactly_at_the_limit(s3):
    client, stubber = s3
    stubber.add_response("get_object", {"Body": _body(b"x" * 5), "ContentLength": 5})

    assert _storage(client, max_bytes=5).get_bytes("docs/ok.bin") == b"x" * 5


def test_other_server_errors_become_storage_errors(s3):
    client, stubber = s3
    stubber.add_client_error("get_object", service_error_code="AccessDenied", http_status_code=403)

    with pytest.raises(StorageError, match="AccessDenied") as error:
        _storage(client).get_bytes("docs/a.pdf")
    assert not isinstance(error.value, ObjectNotFound)


def test_connection_failures_become_storage_errors():
    class Broken:
        def get_object(self, **_):
            raise EndpointConnectionError(endpoint_url="http://s3:9000")

    with pytest.raises(StorageError, match="EndpointConnectionError"):
        ObjectStorage(Broken(), BUCKET, max_bytes=10).get_bytes("docs/a.pdf")


def test_put_bytes_sends_content_and_type(s3):
    client, stubber = s3
    stubber.add_response(
        "put_object",
        {},
        {"Bucket": BUCKET, "Key": "derived/t.txt", "Body": b"text", "ContentType": "text/plain"},
    )

    _storage(client).put_bytes("derived/t.txt", b"text", "text/plain")

    stubber.assert_no_pending_responses()


@pytest.mark.parametrize("key", ["", "/abs", "a\x00b"])
def test_invalid_keys_are_rejected_before_any_request(s3, key):
    client, _ = s3

    with pytest.raises(ValueError):
        _storage(client).get_bytes(key)
    with pytest.raises(ValueError):
        _storage(client).put_bytes(key, b"x")


def test_from_settings_requires_credentials():
    settings = Settings(_env_file=None, **settings_values())

    with pytest.raises(StorageError, match="S3_ACCESS_KEY"):
        ObjectStorage.from_settings(settings)


def test_from_settings_builds_a_path_style_client():
    settings = Settings(_env_file=None, **settings_values(s3_access_key="k", s3_secret_key="s"))

    storage = ObjectStorage.from_settings(settings)

    assert storage._client.meta.config.s3["addressing_style"] == "path"
    assert storage._client.meta.endpoint_url == "http://s3:9000"
