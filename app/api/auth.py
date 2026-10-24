"""Verifies the client-credentials JWT that Spring Boot sends (contract: securitySchemes.serviceToken).

Only Keycloak-signed RS256 tokens issued to the service client are accepted. Tokens are never logged.
"""

from collections.abc import Callable
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.errors import ProblemError
from app.config import Settings, get_settings

ALGORITHMS = ["RS256"]
LEEWAY_SECONDS = 30

KeyResolver = Callable[[str], Any]

# Named like the contract's security scheme so the exported OpenAPI matches it.
_bearer = HTTPBearer(scheme_name="serviceToken", bearerFormat="JWT", auto_error=False)


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=300, timeout=5)


def get_key_resolver(settings: Annotated[Settings, Depends(get_settings)]) -> KeyResolver:
    """Returns a function mapping a raw token to its signing key (Keycloak JWKS, cached)."""
    client = _jwks_client(settings.jwks_url)
    return lambda token: client.get_signing_key_from_jwt(token).key


def _unauthorized() -> ProblemError:
    return ProblemError(
        status.HTTP_401_UNAUTHORIZED,
        "UNAUTHORIZED",
        "Invalid or missing service token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_service_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
    resolve_key: Annotated[KeyResolver, Depends(get_key_resolver)],
) -> dict[str, Any]:
    if credentials is None:
        raise _unauthorized()
    token = credentials.credentials

    try:
        claims = jwt.decode(
            token,
            key=resolve_key(token),
            algorithms=ALGORITHMS,
            issuer=settings.auth_issuer,
            audience=settings.auth_audience,
            leeway=LEEWAY_SECONDS,
            options={
                "require": ["exp", "iss"],
                "verify_aud": settings.auth_audience is not None,
            },
        )
    except jwt.PyJWKClientConnectionError as exc:
        raise ProblemError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "IDP_UNAVAILABLE",
            "Cannot reach the identity provider to verify the token",
        ) from exc
    except jwt.PyJWTError as exc:
        raise _unauthorized() from exc

    if claims.get("azp") != settings.auth_allowed_client:
        raise _unauthorized()
    return claims
