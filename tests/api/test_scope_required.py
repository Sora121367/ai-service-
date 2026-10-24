"""A request without a valid scope is rejected with 400 (CLAUDE.md hard rule 1)."""

from uuid import uuid4

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api.errors import PROBLEM_JSON, register_error_handlers
from app.api.scope import Scope


class SearchRequest(BaseModel):
    scope: Scope
    query: str


class Echo(BaseModel):
    text: str


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    router = APIRouter()

    @router.post("/scoped")
    def scoped(body: SearchRequest) -> dict[str, str]:
        return {"ok": "yes"}

    @router.post("/unscoped")
    def unscoped(body: Echo) -> dict[str, str]:
        return {"ok": "yes"}

    app.include_router(router)
    return TestClient(app)


def valid_scope() -> dict:
    return {
        "scopeType": "course",
        "classroomId": str(uuid4()),
        "courseId": str(uuid4()),
        "documentIds": [str(uuid4())],
    }


def test_valid_scope_is_accepted(client):
    response = client.post("/scoped", json={"scope": valid_scope(), "query": "q"})

    assert response.status_code == 200


@pytest.mark.parametrize("body", [{"query": "q"}, {}, None])
def test_missing_scope_returns_400_problem_details(client, body):
    response = client.post("/scoped", json=body) if body is not None else client.post("/scoped")

    assert response.status_code == 400
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert response.json() == {
        "type": "about:blank",
        "title": "Scope required",
        "status": 400,
        "detail": "The request has no scope.",
        "code": "SCOPE_REQUIRED",
    }


@pytest.mark.parametrize(
    "scope",
    [
        {},
        {**valid_scope(), "documentIds": []},  # an empty selection must not mean "everything"
        {**valid_scope(), "scopeType": "global"},
        {**valid_scope(), "extra": "x"},
    ],
)
def test_invalid_scope_returns_400(client, scope):
    response = client.post("/scoped", json={"scope": scope, "query": "q"})

    assert response.status_code == 400
    assert response.json()["code"] == "SCOPE_INVALID"


def test_error_does_not_echo_the_request(client):
    response = client.post("/scoped", json={"scope": {"scopeType": "secret-text"}, "query": "q"})

    assert "secret-text" not in response.text


def test_other_validation_errors_stay_422(client):
    response = client.post("/scoped", json={"scope": valid_scope()})

    assert response.status_code == 422


def test_endpoints_without_a_scope_field_are_not_affected(client):
    assert client.post("/unscoped", json={}).status_code == 422
    assert client.post("/unscoped").status_code == 422
