"""Object storage in RustFS through boto3 (ADR-0004: S3 API, path-style, endpoint and bucket from config).

Files are shared with the backend and read by reference (spec Section 5). Reads are capped so a
bad reference can't pull an unbounded object into memory. Keys and sizes may be logged; contents
never are (docs/conventions.md, Logging and privacy).
"""

import logging
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings

logger = logging.getLogger("insighthub.storage")

_NOT_FOUND_CODES = {"NoSuchKey", "404", "NotFound"}


class StorageError(RuntimeError):
    """The storage server failed or could not be reached."""


class ObjectNotFound(StorageError):
    pass


class ObjectTooLarge(StorageError):
    pass


class ObjectStorage:
    def __init__(self, client: BaseClient, bucket: str, *, max_bytes: int) -> None:
        self._client = client
        self._bucket = bucket
        self._max_bytes = max_bytes

    @classmethod
    def from_settings(cls, settings: Settings) -> "ObjectStorage":
        if settings.s3_access_key is None or settings.s3_secret_key is None:
            raise StorageError("S3_ACCESS_KEY and S3_SECRET_KEY must be set")
        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key.get_secret_value(),
            aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
            region_name="us-east-1",  # RustFS ignores it; boto3 requires one
            config=Config(
                s3={"addressing_style": "path"},
                connect_timeout=settings.storage_timeout_seconds,
                read_timeout=settings.storage_timeout_seconds,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
        return cls(client, settings.s3_bucket, max_bytes=settings.storage_max_object_bytes)

    def get_bytes(self, key: str) -> bytes:
        """The object's content. Raises ObjectNotFound or ObjectTooLarge."""
        response = self._call("get_object", Bucket=self._bucket, Key=_checked(key))
        length = response.get("ContentLength")
        if length is not None and length > self._max_bytes:
            response["Body"].close()
            raise ObjectTooLarge(f"object is {length} bytes, limit is {self._max_bytes}")
        try:
            with response["Body"] as body:
                data = body.read(self._max_bytes + 1)
        except BotoCoreError as error:
            raise StorageError(f"storage read failed: {type(error).__name__}") from None
        if len(data) > self._max_bytes:
            raise ObjectTooLarge(f"object exceeds the limit of {self._max_bytes} bytes")
        logger.info("read key=%s bytes=%d", key, len(data))
        return data

    def put_bytes(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None:
        """Store derived files (web snapshots, transcripts, converted PDFs)."""
        self._call(
            "put_object",
            Bucket=self._bucket,
            Key=_checked(key),
            Body=data,
            ContentType=content_type,
        )
        logger.info("wrote key=%s bytes=%d", key, len(data))

    def _call(self, operation: str, **params: Any) -> dict[str, Any]:
        try:
            return getattr(self._client, operation)(**params)
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "")
            if code in _NOT_FOUND_CODES:
                raise ObjectNotFound("object not found") from None
            raise StorageError(f"storage request failed: {code or 'ClientError'}") from None
        except BotoCoreError as error:
            raise StorageError(f"storage request failed: {type(error).__name__}") from None


def _checked(key: str) -> str:
    if not key or key.startswith("/") or "\x00" in key:
        raise ValueError("invalid object key")
    return key
