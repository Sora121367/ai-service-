"""Every error the API returns is RFC 9457 problem+json with a stable code and fixed wording."""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.errors import PROBLEM_JSON, ProblemError, register_error_handlers
from app.main import app as real_app

SECRET = "tok-123-secret-user-content"


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/ok")
    def ok() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError(SECRET)

    @app.get("/teapot")
    def teapot() -> None:
        raise HTTPException(418, "short and stout")

    @app.get("/coded")
    def coded() -> None:
        raise ProblemError(409, "DOCUMENT_BUSY", "The document is being processed.")

    return TestClient(app, raise_server_exceptions=False)


def assert_problem(response, status, code):
    assert response.status_code == status
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    body = response.json()
    assert body["status"] == status
    assert body["code"] == code
    assert set(body) == {"type", "title", "status", "detail", "code"}


def test_unknown_route_is_404_not_found(client):
    assert_problem(client.get("/nope"), 404, "NOT_FOUND")


def test_wrong_method_is_405(client):
    assert_problem(client.post("/ok"), 405, "METHOD_NOT_ALLOWED")


def test_plain_http_exception_gets_a_generic_code(client):
    response = client.get("/teapot")

    assert_problem(response, 418, "HTTP_418")
    assert response.json()["detail"] == "short and stout"


def test_problem_error_carries_its_own_code(client):
    response = client.get("/coded")

    assert_problem(response, 409, "DOCUMENT_BUSY")
    assert response.json()["title"] == "Conflict"


def test_unhandled_exception_is_500_without_its_message(client, caplog):
    with caplog.at_level("ERROR", logger="insighthub.api"):
        response = client.get("/boom")

    assert_problem(response, 500, "INTERNAL_ERROR")
    assert SECRET not in response.text
    assert SECRET not in caplog.text
    assert "RuntimeError" in caplog.text


def test_the_real_app_returns_problem_json_for_unknown_routes():
    response = TestClient(real_app).get("/nope")

    assert_problem(response, 404, "NOT_FOUND")
