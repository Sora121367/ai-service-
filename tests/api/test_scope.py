from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from app.api.scope import CourseScope, PersonalScope, Scope

scope_adapter = TypeAdapter(Scope)


def personal(**overrides):
    return {
        "scopeType": "personal",
        "workspaceId": str(uuid4()),
        "ownerId": str(uuid4()),
        "documentIds": [str(uuid4())],
    } | overrides


def course(**overrides):
    return {
        "scopeType": "course",
        "classroomId": str(uuid4()),
        "courseId": str(uuid4()),
        "documentIds": [str(uuid4())],
    } | overrides


def test_parses_personal_scope():
    assert isinstance(scope_adapter.validate_python(personal()), PersonalScope)


def test_parses_course_scope():
    assert isinstance(scope_adapter.validate_python(course()), CourseScope)


def test_scope_is_immutable():
    scope = scope_adapter.validate_python(course())
    with pytest.raises(ValidationError):
        scope.course_id = uuid4()


@pytest.mark.parametrize(
    "payload",
    [
        {k: v for k, v in personal().items() if k != "scopeType"},
        personal(scopeType="admin"),
        personal(documentIds=[]),
        course(documentIds=[]),
        {k: v for k, v in personal().items() if k != "ownerId"},
        {k: v for k, v in course().items() if k != "courseId"},
        personal(extra="x"),
        # course fields must not be smuggled into a personal scope (and vice versa)
        personal(courseId=str(uuid4())),
        course(ownerId=str(uuid4())),
        personal(workspaceId="not-a-uuid"),
        course(documentIds=["not-a-uuid"]),
    ],
    ids=[
        "missing-scope-type",
        "unknown-scope-type",
        "personal-empty-documents",
        "course-empty-documents",
        "personal-missing-owner",
        "course-missing-course",
        "extra-field",
        "personal-with-course-field",
        "course-with-owner-field",
        "bad-workspace-uuid",
        "bad-document-uuid",
    ],
)
def test_rejects_invalid_scope(payload):
    with pytest.raises(ValidationError):
        scope_adapter.validate_python(payload)
