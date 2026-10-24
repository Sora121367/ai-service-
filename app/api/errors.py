"""RFC 9457 Problem Details for errors the API raises itself (docs/conventions.md)."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

PROBLEM_JSON = "application/problem+json"


def problem(status: int, title: str, code: str, detail: str) -> JSONResponse:
    body = {"type": "about:blank", "title": title, "status": status, "detail": detail, "code": code}
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON)


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
    errors = [{"loc": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
    return JSONResponse({"detail": errors}, status_code=422)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_error)  # type: ignore[arg-type]
