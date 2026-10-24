from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app

ISSUER = "http://localhost:8180/realms/insighthub"
CLIENT_ID = "insighthub-ai-caller"


def settings_values(**overrides: Any) -> dict[str, Any]:
    """Every required Settings field, so a test only spells out what it cares about."""
    return {
        "database_url": "postgresql://x/db",
        "redis_url": "redis://redis:6379",
        "ollama_url": "http://ollama:11434",
        "s3_endpoint": "http://s3:9000",
        "s3_bucket": "test-bucket",
        "auth_issuer": ISSUER,
        "auth_allowed_client": CLIENT_ID,
    } | overrides


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
