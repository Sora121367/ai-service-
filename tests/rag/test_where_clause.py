from uuid import uuid4

import pytest

from app.api.scope import CourseScope, PersonalScope
from app.rag.scope_filter import ScopeFilter, scope_filter, where_clause


def test_personal_scope_filters_on_type_workspace_owner_and_documents():
    document, workspace, owner = uuid4(), uuid4(), uuid4()
    scope = PersonalScope.model_validate(
        {
            "scopeType": "personal",
            "workspaceId": workspace,
            "ownerId": owner,
            "documentIds": [document],
        }
    )

    sql, params = where_clause(scope_filter(scope))

    assert sql == (
        "scope_type = :scope_0 AND workspace_id = :scope_1 AND owner_id = :scope_2 "
        "AND document_id = ANY(CAST(:scope_document_ids AS uuid[]))"
    )
    assert params == {
        "scope_0": "personal",
        "scope_1": workspace,
        "scope_2": owner,
        "scope_document_ids": [document],
    }


def test_course_scope_filters_on_type_classroom_course_and_documents():
    classroom, course, document = uuid4(), uuid4(), uuid4()
    scope = CourseScope.model_validate(
        {
            "scopeType": "course",
            "classroomId": classroom,
            "courseId": course,
            "documentIds": [document],
        }
    )

    sql, params = where_clause(scope_filter(scope))

    assert sql.startswith(
        "scope_type = :scope_0 AND classroom_id = :scope_1 AND course_id = :scope_2"
    )
    assert params["scope_1"] == classroom
    assert params["scope_2"] == course


def test_values_are_parameters_never_part_of_the_sql():
    marker = uuid4()
    scope = PersonalScope.model_validate(
        {
            "scopeType": "personal",
            "workspaceId": marker,
            "ownerId": marker,
            "documentIds": [marker],
        }
    )

    sql, _ = where_clause(scope_filter(scope))

    assert str(marker) not in sql


def test_an_unknown_column_is_refused():
    with pytest.raises(ValueError, match="not a scope column"):
        where_clause(ScopeFilter(equals={"1=1 --": "x"}, document_ids=frozenset({uuid4()})))


def test_an_empty_document_selection_is_refused():
    with pytest.raises(ValueError, match="at least one document"):
        where_clause(ScopeFilter(equals={"scope_type": "personal"}, document_ids=frozenset()))
