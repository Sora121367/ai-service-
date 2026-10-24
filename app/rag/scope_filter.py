"""The one place that turns a Scope into search filters (CLAUDE.md hard rule 1).

Every vector and keyword search builds its WHERE clause from `scope_filter(scope)`. The filter
only ever narrows: it never adds ids the caller didn't send, and an unknown scope type is an
error, not an open filter. Column names match the chunks table (docs/conventions.md).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.api.scope import CourseScope, PersonalScope


@dataclass(frozen=True)
class ScopeFilter:
    equals: Mapping[str, str | UUID]  # column -> required value
    document_ids: frozenset[UUID]  # `document_id` must be one of these (never empty)

    def matches(self, row: Mapping[str, Any]) -> bool:
        """Reference semantics, used by tests. The SQL built from this filter must agree."""
        return (
            all(row.get(column) == value for column, value in self.equals.items())
            and row.get("document_id") in self.document_ids
        )


def scope_filter(scope: PersonalScope | CourseScope) -> ScopeFilter:
    match scope:
        case PersonalScope():
            equals = {
                "scope_type": "personal",
                "workspace_id": scope.workspace_id,
                "owner_id": scope.owner_id,
            }
        case CourseScope():
            equals = {
                "scope_type": "course",
                "classroom_id": scope.classroom_id,
                "course_id": scope.course_id,
            }
        case _:
            raise TypeError(f"Unsupported scope: {type(scope).__name__}")
    return ScopeFilter(equals=equals, document_ids=frozenset(scope.document_ids))


_COLUMNS = frozenset({"scope_type", "classroom_id", "course_id", "workspace_id", "owner_id"})


def where_clause(selected: ScopeFilter) -> tuple[str, dict[str, Any]]:
    """The SQL form of a ScopeFilter: a WHERE condition with named parameters. Always narrows.

    Column names come from `scope_filter` only and are checked against the scope columns, so
    nothing a caller sends is ever interpolated into the SQL.
    """
    if not selected.document_ids:
        raise ValueError("a scope filter needs at least one document id")
    conditions: list[str] = []
    params: dict[str, Any] = {}
    for position, (column, value) in enumerate(selected.equals.items()):
        if column not in _COLUMNS:
            raise ValueError(f"not a scope column: {column}")
        conditions.append(f"{column} = :scope_{position}")
        params[f"scope_{position}"] = value
    conditions.append("document_id = ANY(CAST(:scope_document_ids AS uuid[]))")
    params["scope_document_ids"] = sorted(selected.document_ids, key=str)
    return " AND ".join(conditions), params
