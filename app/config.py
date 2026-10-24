from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_SERVICE_DIR = Path(__file__).resolve().parent.parent

# Repo-root .env only (copied from .env.example). Nothing outside this repo is read.
ENV_FILES = (_SERVICE_DIR / ".env",)


class Settings(BaseSettings):
    """Deployment config. Values come from the environment or .env (gitignored)."""

    model_config = SettingsConfigDict(env_file=ENV_FILES, extra="ignore")

    database_url: str  # vector DB, owned by this service; no default (holds credentials)
    redis_url: str
    ollama_url: str

    # Object storage (S3 API). Keys are optional until the first S3 client exists.
    s3_endpoint: str
    s3_bucket: str
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None

    # Service-token auth: Spring Boot calls with a client-credentials token from Keycloak.
    auth_issuer: str  # must equal the token's `iss`
    auth_jwks_url: str | None = None  # where to fetch signing keys; set it inside containers
    auth_audience: str | None = None  # checked only when set (needs a realm audience mapper)
    auth_allowed_client: str  # the token's `azp`

    # This service's own client for calling back the backend (ADR-0003).
    backend_callback_url: str | None = None
    callback_client_id: str | None = None
    callback_client_secret: SecretStr | None = None

    # Models are decided in spec Section 11; they fix the vector dimension.
    llm_model: str | None = None
    embedding_model: str | None = None
    web_search_api_key: SecretStr | None = None

    @property
    def jwks_url(self) -> str:
        if self.auth_jwks_url:
            return self.auth_jwks_url
        return f"{self.auth_issuer.rstrip('/')}/protocol/openid-connect/certs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
