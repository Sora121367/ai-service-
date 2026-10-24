from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.config import Settings
from tests.conftest import settings_values

ROOT = Path(__file__).resolve().parents[1]


def test_alembic_finds_the_migrations_folder_with_no_revisions_yet():
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))

    assert Path(script.dir) == ROOT / "migrations"
    assert script.get_heads() == []


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        (
            "postgresql://ai:ai@localhost:5433/vectors",
            "postgresql+psycopg://ai:ai@localhost:5433/vectors",
        ),
        ("postgres://ai:ai@db/vectors", "postgresql+psycopg://ai:ai@db/vectors"),
        ("postgresql+psycopg://ai:ai@db/vectors", "postgresql+psycopg://ai:ai@db/vectors"),
    ],
)
def test_sqlalchemy_url_uses_the_psycopg_driver(configured, expected):
    settings = Settings(_env_file=None, **settings_values(database_url=configured))

    assert settings.sqlalchemy_url == expected


def test_alembic_ini_holds_no_database_url():
    text = (ROOT / "alembic.ini").read_text(encoding="utf-8")

    assert "sqlalchemy.url" not in text
