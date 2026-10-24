import pytest
from pydantic import ValidationError

from app import config
from app.config import Settings
from tests.conftest import ISSUER, settings_values

ENV_NAMES = [name.upper() for name in Settings.model_fields]
REQUIRED = list(settings_values())


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def write_env(tmp_path, values):
    env_file = tmp_path / ".env"
    env_file.write_text("".join(f"{k.upper()}={v}\n" for k, v in values.items()))
    return env_file


def test_reads_values_from_env_file(tmp_path):
    env_file = write_env(
        tmp_path, settings_values(database_url="postgresql://ai:ai@localhost:5433/vectors")
    )

    settings = Settings(_env_file=env_file)

    assert settings.database_url == "postgresql://ai:ai@localhost:5433/vectors"
    assert settings.auth_issuer == ISSUER
    assert settings.auth_allowed_client == "insighthub-ai-caller"
    assert settings.llm_model is None


def test_environment_overrides_env_file(tmp_path, monkeypatch):
    env_file = write_env(tmp_path, settings_values(database_url="postgresql://from-file/db"))
    monkeypatch.setenv("DATABASE_URL", "postgresql://from-env/db")

    assert Settings(_env_file=env_file).database_url == "postgresql://from-env/db"


@pytest.mark.parametrize("missing", REQUIRED)
def test_required_settings(tmp_path, missing):
    values = settings_values()
    del values[missing]

    with pytest.raises(ValidationError, match=missing):
        Settings(_env_file=write_env(tmp_path, values))


def test_jwks_url_defaults_to_issuer_certs_endpoint():
    settings = Settings(_env_file=None, **settings_values())

    assert settings.jwks_url == f"{ISSUER}/protocol/openid-connect/certs"


def test_jwks_url_can_be_overridden_for_containers():
    url = "http://keycloak:8080/realms/insighthub/protocol/openid-connect/certs"
    settings = Settings(_env_file=None, **settings_values(auth_jwks_url=url))

    assert settings.jwks_url == url


def test_secrets_are_not_printed():
    settings = Settings(
        _env_file=None,
        **settings_values(
            s3_secret_key="s3-secret", callback_client_secret="cb-secret", web_search_api_key="key"
        ),
    )

    text = repr(settings)

    assert "s3-secret" not in text
    assert "cb-secret" not in text
    assert "key'" not in text
    assert settings.s3_secret_key.get_secret_value() == "s3-secret"


def test_only_the_repo_root_env_file_is_read():
    assert [p.name for p in config.ENV_FILES] == [".env"]
    assert all(p.parent == config._SERVICE_DIR for p in config.ENV_FILES)
