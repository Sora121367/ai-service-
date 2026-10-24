"""RFC 9457 Problem Details for every error the API returns (docs/conventions.md).

Bodies hold a stable `code` and fixed wording only: never request content, file text, tokens,
addresses or exception messages.
"""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_JSON = "application/problem+json"

logger = logging.getLogger("insighthub.api")

# `code` for errors raised by the framework (unknown route, wrong method) or plain HTTPExceptions.
_CODES = {401: "UNAUTHORIZED", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


class ProblemError(HTTPException):
    """An HTTPException that carries its own stable `code`."""

    def __init__(
        self, status_code: int, code: str, detail: str, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code


def _title(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def problem(
    status: int,
    title: str,
    code: str,
    detail: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = {"type": "about:blank", "title": title, "status": status, "detail": detail, "code": code}
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


def _takes_scope(request: Request) -> bool:
    """True when the matched route's request body has a `scope` field."""
    field = getattr(request.scope.get("route"), "body_field", None)
    model = field.field_info.annotation if field is not None else None
    return "scope" in getattr(model, "model_fields", {})


def _scope_problem(request: Request, errors: list[Any]) -> JSONResponse | None:
    if not _takes_scope(request):
        return None
    for error in errors:
        loc = tuple(error["loc"])
        if loc == ("body",) or loc[:2] == ("body", "scope"):
            missing = error["type"] == "missing" and len(loc) <= 2
            if missing:
                return problem(400, "Scope required", "SCOPE_REQUIRED", "The request has no scope.")
            return problem(400, "Invalid scope", "SCOPE_INVALID", "The request scope is invalid.")
    return None


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Never echo the input back: it may hold user content.
    if (response := _scope_problem(request, exc.errors())) is not None:
        return response
    return problem(400, "Invalid request", "INVALID_REQUEST", "The request is invalid.")


async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = getattr(exc, "code", None) or _CODES.get(exc.status_code, f"HTTP_{exc.status_code}")
    return problem(
        exc.status_code,
        _title(exc.status_code),
        code,
        str(exc.detail),
        headers=dict(exc.headers) if exc.headers else None,
    )


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    # Log the type and route only: the message may hold user content.
    logger.error("unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path)
    return problem(
        500, "Internal Server Error", "INTERNAL_ERROR", "The service failed unexpectedly."
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_error)
