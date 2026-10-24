"""Fail when the API the code exports differs from contracts/ai-service.yaml (CLAUDE.md rule 3).

Run from the repo root: `uv run python -m scripts.contract_check [contract.yaml]`.

What is compared, per operation: the operationId, effective security, parameters, request body
and response schemas (with $refs resolved) and the status codes. Wording is ignored: titles,
descriptions, summaries, examples, `deprecated`, servers and the info block.

Rules that make the comparison fit a contract-first workflow:
- A response the contract declares without content only has its status code checked; the code may
  describe the body in more detail.
- FastAPI adds a 422 to routes with a request body. It is ignored unless the contract declares it.
- An operation marked `x-pending-implementation: true` in the contract may be absent from the code
  (the contract PR merges before the implementation PR). Once the code has it, it is compared.
- Schemas nobody references from an operation are not compared.
"""

import json
import sys
from pathlib import Path
from typing import Any

import yaml

CONTRACT = Path(__file__).resolve().parents[1] / "contracts" / "ai-service.yaml"
METHODS = ("get", "put", "post", "delete", "patch", "head", "options")
WORDING = {"title", "description", "summary", "example", "examples", "externalDocs", "deprecated"}
SCHEMA_MAPS = {"properties", "patternProperties", "$defs", "definitions"}
SCHEMA_LISTS = {"oneOf", "anyOf", "allOf"}
IGNORED_CODE_STATUSES = {"422"}


def _lookup(doc: dict[str, Any], ref: str) -> Any:
    node: Any = doc
    for part in ref.removeprefix("#/").split("/"):
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def normalize(node: Any, doc: dict[str, Any], seen: tuple[str, ...] = ()) -> Any:
    """A schema (or any node) with $refs resolved and wording removed, in a stable order."""
    if isinstance(node, list):
        return [normalize(item, doc, seen) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        ref = node["$ref"]
        if ref in seen:
            return {"$cycle": ref.rsplit("/", 1)[-1]}
        return normalize(_lookup(doc, ref), doc, (*seen, ref))
    result: dict[str, Any] = {}
    for key, value in node.items():
        if key in WORDING:
            continue
        if key in SCHEMA_MAPS and isinstance(value, dict):
            # Keys here are property names, so a property called "title" must survive.
            result[key] = {name: normalize(sub, doc, seen) for name, sub in value.items()}
        elif key in SCHEMA_LISTS and isinstance(value, list):
            result[key] = sorted((normalize(sub, doc, seen) for sub in value), key=_canon)
        elif key in {"required", "enum"} and isinstance(value, list):
            result[key] = sorted(value, key=_canon)
        elif key == "type" and isinstance(value, list):
            result[key] = sorted(value)
        else:
            result[key] = normalize(value, doc, seen)
    return result


def _security(operation: dict[str, Any], doc: dict[str, Any]) -> list[list[str]]:
    requirements = operation["security"] if "security" in operation else doc.get("security", [])
    return sorted(sorted(requirement) for requirement in requirements)


def _content(block: dict[str, Any] | None, doc: dict[str, Any]) -> dict[str, Any] | None:
    if not block or not block.get("content"):
        return None
    return {
        media.split(";")[0]: normalize(body.get("schema"), doc)
        for media, body in block["content"].items()
    }


def _parameters(path_item: dict[str, Any], operation: dict[str, Any], doc: dict[str, Any]):
    merged: dict[tuple[str, str], Any] = {}
    for raw in [*path_item.get("parameters", []), *operation.get("parameters", [])]:
        parameter = _lookup(doc, raw["$ref"]) if "$ref" in raw else raw
        merged[(parameter["in"], parameter["name"])] = {
            "required": bool(parameter.get("required", False)),
            "schema": normalize(parameter.get("schema"), doc),
        }
    return {f"{where}:{name}": merged[(where, name)] for where, name in sorted(merged)}


def operations(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """`METHOD /path` -> comparable description of the operation."""
    found: dict[str, dict[str, Any]] = {}
    for path, item in (doc.get("paths") or {}).items():
        for method in METHODS:
            if method not in item:
                continue
            op = item[method]
            body = op.get("requestBody")
            if body and "$ref" in body:
                body = _lookup(doc, body["$ref"])
            responses = {}
            for status, response in (op.get("responses") or {}).items():
                if "$ref" in response:
                    response = _lookup(doc, response["$ref"])
                responses[str(status)] = _content(response, doc)
            found[f"{method.upper()} {path}"] = {
                "operationId": op.get("operationId"),
                "security": _security(op, doc),
                "parameters": _parameters(item, op, doc),
                "requestBody": None
                if not body
                else {
                    "required": bool(body.get("required", False)),
                    "content": _content(body, doc),
                },
                "responses": responses,
                "pending": bool(op.get("x-pending-implementation", False)),
            }
    return found


def _schemes(doc: dict[str, Any], used: set[str]) -> dict[str, Any]:
    declared = (doc.get("components") or {}).get("securitySchemes") or {}
    return {
        name: {k: v for k, v in scheme.items() if k not in WORDING}
        for name, scheme in declared.items()
        if name in used
    }


def _compare_responses(contract: dict[str, Any], code: dict[str, Any]) -> list[str]:
    problems = []
    for status, expected in contract.items():
        if status not in code:
            problems.append(f"response {status} is in the contract but not in the code")
        elif expected is not None and expected != code[status]:
            problems.append(
                f"response {status} body differs\n    contract: {_canon(expected)}"
                f"\n    code:     {_canon(code[status])}"
            )
    for status in code.keys() - contract.keys():
        if status not in IGNORED_CODE_STATUSES:
            problems.append(f"response {status} is in the code but not in the contract")
    return problems


def check(contract: dict[str, Any], code: dict[str, Any]) -> list[str]:
    """Every difference that matters, as readable lines. Empty means they agree."""
    expected, actual = operations(contract), operations(code)
    problems: list[str] = []

    for name in sorted(expected.keys() | actual.keys()):
        if name not in actual:
            if not expected[name]["pending"]:
                problems.append(f"{name}: in the contract but not implemented")
            continue
        if name not in expected:
            problems.append(f"{name}: in the code but not in the contract")
            continue
        want, have = expected[name], actual[name]
        for field in ("operationId", "security", "parameters", "requestBody"):
            if want[field] != have[field]:
                problems.append(
                    f"{name}: {field} differs\n    contract: {_canon(want[field])}"
                    f"\n    code:     {_canon(have[field])}"
                )
        problems += [
            f"{name}: {p}" for p in _compare_responses(want["responses"], have["responses"])
        ]

    # Only operations the code has: a pending one can't show its scheme in the code's OpenAPI yet.
    used = {
        scheme
        for name, op in expected.items()
        if name in actual
        for req in op["security"]
        for scheme in req
    }
    if _schemes(contract, used) != _schemes(code, used):
        problems.append(
            f"securitySchemes differ\n    contract: {_canon(_schemes(contract, used))}"
            f"\n    code:     {_canon(_schemes(code, used))}"
        )
    return problems


def main(argv: list[str]) -> int:
    from app.main import app

    path = Path(argv[0]) if argv else CONTRACT
    contract = yaml.safe_load(path.read_text(encoding="utf-8"))
    problems = check(contract, app.openapi())
    if problems:
        print(f"The code's OpenAPI differs from {path.name}:\n", file=sys.stderr)
        print("\n".join(f"- {p}" for p in problems), file=sys.stderr)
        print("\nChange the YAML first (/contract-change), then the code.", file=sys.stderr)
        return 1
    print(f"OK: the code's OpenAPI matches {path.name} ({len(operations(contract))} operations)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
