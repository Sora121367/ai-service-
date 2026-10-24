"""Database fixtures. DB tests run only when TEST_DATABASE_URL points at a throwaway pgvector database.

    docker compose up -d vector-db
    TEST_DATABASE_URL=postgresql://ai:ai@localhost:5433/vectors_test uv run pytest -m db

The database name must contain "test": the tests truncate the chunks table.
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import Settings, get_settings
from app.rag.repository import ChunkRepository
from tests.conftest import settings_values

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def db_engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    if "test" not in (make_url(url).database or ""):
        pytest.fail(
            "TEST_DATABASE_URL must name a throwaway database (its name must contain 'test')"
        )

    patch = pytest.MonkeyPatch()
    for name, value in settings_values(database_url=url).items():
        patch.setenv(name.upper(), str(value))
    get_settings.cache_clear()
    try:
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    finally:
        patch.undo()
        get_settings.cache_clear()

    engine = create_engine(
        Settings(_env_file=None, **settings_values(database_url=url)).sqlalchemy_url
    )
    yield engine
    engine.dispose()


@pytest.fixture
def repository(db_engine) -> ChunkRepository:
    with db_engine.begin() as connection:
        connection.execute(text("TRUNCATE chunks"))
    return ChunkRepository(db_engine)
