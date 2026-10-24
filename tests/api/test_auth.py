import time
from typing import Annotated, Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.auth import get_key_resolver, require_service_token
from app.api.routing import include_protected
from app.config import Settings, get_settings
from app.main import app as real_app
from tests.conftest import CLIENT_ID, ISSUER, settings_values


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def other_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **settings_values(**overrides))


def build_client(signing_key, settings: Settings | None = None, resolver=None) -> TestClient:
    app = FastAPI()

    @app.get("/protected")
    def protected(claims: Annotated[dict[str, Any], Depends(require_service_token)]):
        return {"azp": claims["azp"]}

    def default_resolver(_token):
        return signing_key.public_key()

    app.dependency_overrides[get_settings] = lambda: settings or make_settings()
    app.dependency_overrides[get_key_resolver] = lambda: resolver or default_resolver
    return TestClient(app)


def claims(**overrides) -> dict[str, Any]:
    now = int(time.time())
    return {"iss": ISSUER, "azp": CLIENT_ID, "iat": now, "exp": now + 300} | overrides


def sign(key, payload: dict[str, Any], algorithm: str = "RS256") -> str:
    return jwt.encode(payload, key, algorithm=algorithm)


def call(client: TestClient, token: str | None = None, scheme: str = "Bearer"):
    headers = {"Authorization": f"{scheme} {token}"} if token is not None else {}
    return client.get("/protected", headers=headers)


def assert_unauthorized(response):
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_accepts_valid_service_token(signing_key):
    response = call(build_client(signing_key), sign(signing_key, claims()))

    assert response.status_code == 200
    assert response.json() == {"azp": CLIENT_ID}


def test_rejects_missing_header(signing_key):
    assert_unauthorized(call(build_client(signing_key)))


def test_rejects_non_bearer_scheme(signing_key):
    assert_unauthorized(call(build_client(signing_key), sign(signing_key, claims()), "Basic"))


def test_rejects_garbage_token(signing_key):
    assert_unauthorized(call(build_client(signing_key), "not-a-jwt"))


def test_rejects_token_signed_by_other_key(signing_key, other_key):
    assert_unauthorized(call(build_client(signing_key), sign(other_key, claims())))


def test_rejects_expired_token(signing_key):
    expired = claims(exp=int(time.time()) - 120)

    assert_unauthorized(call(build_client(signing_key), sign(signing_key, expired)))


def test_rejects_token_without_exp(signing_key):
    payload = claims()
    del payload["exp"]

    assert_unauthorized(call(build_client(signing_key), sign(signing_key, payload)))


def test_rejects_wrong_issuer(signing_key):
    payload = claims(iss="http://evil.example/realms/insighthub")

    assert_unauthorized(call(build_client(signing_key), sign(signing_key, payload)))


@pytest.mark.parametrize("azp", ["insighthub-web", "insighthub-mobile", None])
def test_rejects_token_from_other_client(signing_key, azp):
    payload = claims(azp=azp)
    if azp is None:
        del payload["azp"]

    assert_unauthorized(call(build_client(signing_key), sign(signing_key, payload)))


def test_rejects_unsigned_token(signing_key):
    token = jwt.encode(claims(), key=None, algorithm="none")

    assert_unauthorized(call(build_client(signing_key), token))


def test_rejects_hs256_token(signing_key):
    token = sign("a-shared-secret-at-least-32-bytes-long!!", claims(), algorithm="HS256")

    assert_unauthorized(call(build_client(signing_key), token))


def test_ignores_audience_when_not_configured(signing_key):
    token = sign(signing_key, claims(aud="account"))

    assert call(build_client(signing_key), token).status_code == 200


def test_checks_audience_when_configured(signing_key):
    client = build_client(signing_key, make_settings(auth_audience="insighthub-ai-service"))

    assert call(client, sign(signing_key, claims(aud="insighthub-ai-service"))).status_code == 200
    assert_unauthorized(call(client, sign(signing_key, claims(aud="account"))))
    assert_unauthorized(call(client, sign(signing_key, claims())))


def test_returns_503_when_keycloak_unreachable(signing_key):
    def unreachable(_token):
        raise jwt.PyJWKClientConnectionError("connection refused")

    response = call(build_client(signing_key, resolver=unreachable), sign(signing_key, claims()))

    assert response.status_code == 503


PUBLIC_PATHS = {"/health"}


def unprotected_operations(app: FastAPI) -> list[str]:
    """Operations without the serviceToken requirement, read from the exported OpenAPI.

    Uses the spec rather than app.routes: included routers are not flattened into app.routes.
    """
    spec = app.openapi()
    return [
        f"{method.upper()} {path}"
        for path, operations in spec.get("paths", {}).items()
        if path not in PUBLIC_PATHS
        for method, operation in operations.items()
        if {"serviceToken": []} not in operation.get("security", [])
    ]


def test_every_route_except_health_requires_service_token():
    assert unprotected_operations(real_app) == []


def test_guard_detects_unprotected_routes():
    app = FastAPI()
    protected, unprotected = APIRouter(), APIRouter()
    protected.get("/good")(lambda: 1)
    unprotected.get("/bad")(lambda: 2)
    include_protected(protected, target=app)
    app.include_router(unprotected)
    app.get("/bad-direct")(lambda: 3)

    assert unprotected_operations(app) == ["GET /bad", "GET /bad-direct"]


def test_security_scheme_matches_contract():
    app = FastAPI()
    app.get("/x", dependencies=[Depends(require_service_token)])(lambda: 1)

    scheme = app.openapi()["components"]["securitySchemes"]["serviceToken"]

    assert scheme == {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
