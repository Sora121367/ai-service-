"""Guard for hard rule 1: no search function without a Scope argument may exist.

Scans app/ for functions that look like a search or retrieval and fails if one has no `scope`
parameter. Extend SEARCH_NAME if a search function is named differently.
"""

import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
SEARCH_NAME = re.compile(r"search|retriev|similar|nearest|knn|hybrid|query_chunks", re.IGNORECASE)


def unscoped_searches(source: str, filename: str = "<memory>") -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source, filename)):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not SEARCH_NAME.search(node.name):
            continue
        args = node.args
        names = {a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]}
        if "scope" not in names:
            found.append(f"{filename}:{node.lineno} {node.name}")
    return found


def test_every_search_function_in_app_takes_a_scope():
    offenders = []
    for path in APP.rglob("*.py"):
        offenders += unscoped_searches(path.read_text(encoding="utf-8"), str(path.relative_to(APP)))
    assert offenders == []


def test_the_guard_catches_a_search_without_scope():
    assert unscoped_searches("def search_chunks(query, top_k): ...")
    assert unscoped_searches("async def retrieve(query): ...")


def test_the_guard_accepts_a_scoped_search():
    assert unscoped_searches("def search_chunks(scope, query): ...") == []
    assert unscoped_searches("def vector_search(query, *, scope): ...") == []
