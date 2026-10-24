import copy

import yaml
from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from app.api.errors import register_error_handlers
from app.api.routing import include_protected
from app.api.scope import Scope
from app.main import app
from scripts.contract_check import CONTRACT, check, main

BEARER = {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}


def spec(paths, schemas=None, security=None):
    return {
        "openapi": "3.1.0",
        "info": {"title": "t", "version": "1.0.0"},
        "security": security if security is not None else [{"serviceToken": []}],
        "paths": paths,
        "components": {"securitySchemes": {"serviceToken": BEARER}, "schemas": schemas or {}},
    }


HEALTH = {
    "get": {"operationId": "health", "security": [], "responses": {"200": {"description": "OK"}}}
}


def test_the_real_contract_matches_the_real_app():
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))

    assert check(contract, app.openapi()) == []
    assert main([]) == 0


def test_wording_differences_are_ignored():
    contract = spec({"/health": HEALTH})
    code = copy.deepcopy(contract)
    code["info"]["description"] = "something else"
    code["paths"]["/health"]["get"]["summary"] = "Health"
    code["paths"]["/health"]["get"]["responses"]["200"] = {
        "description": "Successful Response",
        "content": {"application/json": {"schema": {"type": "object", "title": "Response Health"}}},
    }

    assert check(contract, code) == []


def test_operation_only_in_the_code_fails():
    contract = spec({"/health": HEALTH})
    code = spec({"/health": HEALTH, "/extra": {"get": {"operationId": "extra", "responses": {}}}})

    assert any(
        "GET /extra: in the code but not in the contract" in p for p in check(contract, code)
    )


def test_operation_only_in_the_contract_fails_unless_pending():
    contract = spec(
        {"/health": HEALTH, "/later": {"get": {"operationId": "later", "responses": {}}}}
    )
    code = spec({"/health": HEALTH})

    assert any(
        "GET /later: in the contract but not implemented" in p for p in check(contract, code)
    )

    contract["paths"]["/later"]["get"]["x-pending-implementation"] = True
    assert check(contract, code) == []


def test_pending_operation_is_compared_once_the_code_has_it():
    later = {"operationId": "later", "x-pending-implementation": True, "responses": {"200": {}}}
    contract = spec({"/later": {"get": later}})
    code = spec({"/later": {"get": {"operationId": "other", "responses": {"200": {}}}}})

    assert any("operationId differs" in p for p in check(contract, code))


def test_security_difference_fails():
    contract = spec({"/health": HEALTH})
    code = spec({"/health": {"get": {**HEALTH["get"], "security": [{"serviceToken": []}]}}})

    assert any("security differs" in p for p in check(contract, code))


def test_inherited_global_security_equals_the_same_security_on_the_operation():
    inherited = {"get": {"operationId": "a", "responses": {"200": {}}}}
    explicit = {
        "get": {"operationId": "a", "security": [{"serviceToken": []}], "responses": {"200": {}}}
    }

    assert check(spec({"/a": inherited}), spec({"/a": explicit})) == []


def test_response_status_differences_fail_but_framework_422_is_ignored():
    contract = spec({"/a": {"get": {"operationId": "a", "responses": {"200": {}, "404": {}}}}})
    code = spec({"/a": {"get": {"operationId": "a", "responses": {"200": {}, "422": {}}}}})

    problems = check(contract, code)

    assert any("response 404 is in the contract but not in the code" in p for p in problems)
    assert not any("422" in p for p in problems)


def test_a_422_the_contract_declares_must_exist():
    contract = spec({"/a": {"get": {"operationId": "a", "responses": {"200": {}, "422": {}}}}})
    code = spec({"/a": {"get": {"operationId": "a", "responses": {"200": {}}}}})

    assert any("response 422 is in the contract" in p for p in check(contract, code))


def operation_with_schema(schema_ref_target):
    return {
        "post": {
            "operationId": "make",
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Body"}}},
            },
            "responses": {"202": {}},
        }
    }, {"Body": schema_ref_target}


def test_request_schema_differences_fail_with_refs_resolved():
    op, schemas = operation_with_schema(
        {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}}}
    )
    contract = spec({"/make": op}, schemas)
    same = spec({"/make": op}, {"Body": {**schemas["Body"], "title": "Body", "description": "x"}})
    changed = spec(
        {"/make": op},
        {"Body": {"type": "object", "required": ["a"], "properties": {"a": {"type": "integer"}}}},
    )

    assert check(contract, same) == []
    assert any("requestBody differs" in p for p in check(contract, changed))


def test_property_named_like_a_wording_key_is_still_compared():
    op, schemas = operation_with_schema(
        {"type": "object", "properties": {"title": {"type": "string"}}}
    )
    other = {"type": "object", "properties": {"title": {"type": "integer"}}}

    problems = check(spec({"/make": op}, schemas), spec({"/make": op}, {"Body": other}))

    assert any("requestBody differs" in p for p in problems)


def test_required_and_union_order_does_not_matter():
    a = {
        "type": "object",
        "required": ["x", "y"],
        "oneOf": [{"type": "string"}, {"type": "integer"}],
    }
    b = {
        "type": "object",
        "required": ["y", "x"],
        "oneOf": [{"type": "integer"}, {"type": "string"}],
    }
    op, schemas = operation_with_schema(a)

    assert check(spec({"/make": op}, schemas), spec({"/make": op}, {"Body": b})) == []


def test_scope_in_a_request_matches_a_hand_written_contract():
    """A router built with the real Scope model produces what the contract schemas describe."""

    class SearchRequest(BaseModel):
        scope: Scope
        query: str

    code_app = FastAPI()
    register_error_handlers(code_app)
    router = APIRouter()

    @router.post("/search", operation_id="search", status_code=200)
    def search(body: SearchRequest) -> dict[str, str]:
        return {}

    include_protected(router, code_app)
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    schemas = contract["components"]["schemas"]
    contract["paths"] = {
        "/search": {
            "post": {
                "operationId": "search",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["scope", "query"],
                                "properties": {
                                    "scope": {"$ref": "#/components/schemas/Scope"},
                                    "query": {"type": "string"},
                                },
                            }
                        }
                    },
                },
                "responses": {"200": {}},
            }
        }
    }
    del schemas["JobStatus"]

    assert check(contract, code_app.openapi()) == []


def test_security_scheme_of_a_pending_operation_is_not_required_in_the_code():
    pending = {"get": {"operationId": "later", "x-pending-implementation": True, "responses": {}}}
    contract = spec({"/health": HEALTH, "/later": pending})
    code = spec({"/health": HEALTH})
    code["components"]["securitySchemes"] = {}

    assert check(contract, code) == []
