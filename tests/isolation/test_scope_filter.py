"""Isolation (spec Section 5): a scope only ever sees its own chunks.

These run the reference semantics of ScopeFilter over an in-memory corpus. When the chunks table
and the SQL search exist, run the same scenarios against the database (README in this folder).
"""

from uuid import uuid4

import pytest

from app.api.scope import CourseScope, PersonalScope
from app.rag.scope_filter import scope_filter

ALICE, BOB = uuid4(), uuid4()
ALICE_WS, BOB_WS = uuid4(), uuid4()
CLASSROOM_A, CLASSROOM_B = uuid4(), uuid4()
COURSE_1, COURSE_2 = uuid4(), uuid4()


def personal_chunk(owner, workspace, document):
    return {
        "scope_type": "personal",
        "owner_id": owner,
        "workspace_id": workspace,
        "classroom_id": None,
        "course_id": None,
        "document_id": document,
    }


def course_chunk(classroom, course, document):
    return {
        "scope_type": "course",
        "owner_id": None,
        "workspace_id": None,
        "classroom_id": classroom,
        "course_id": course,
        "document_id": document,
    }


DOC_ALICE, DOC_ALICE_2, DOC_BOB = uuid4(), uuid4(), uuid4()
DOC_C1, DOC_C1_OTHER, DOC_C2, DOC_B = uuid4(), uuid4(), uuid4(), uuid4()

CORPUS = [
    personal_chunk(ALICE, ALICE_WS, DOC_ALICE),
    personal_chunk(ALICE, ALICE_WS, DOC_ALICE_2),
    personal_chunk(BOB, BOB_WS, DOC_BOB),
    course_chunk(CLASSROOM_A, COURSE_1, DOC_C1),
    course_chunk(CLASSROOM_A, COURSE_1, DOC_C1_OTHER),
    course_chunk(CLASSROOM_A, COURSE_2, DOC_C2),
    course_chunk(CLASSROOM_B, COURSE_1, DOC_B),
]


def search(scope):
    selected = scope_filter(scope)
    return {row["document_id"] for row in CORPUS if selected.matches(row)}


def personal(documents, owner=ALICE, workspace=ALICE_WS):
    return PersonalScope.model_validate(
        {
            "scopeType": "personal",
            "ownerId": owner,
            "workspaceId": workspace,
            "documentIds": documents,
        }
    )


def course(documents, classroom=CLASSROOM_A, course_id=COURSE_1):
    return CourseScope.model_validate(
        {
            "scopeType": "course",
            "classroomId": classroom,
            "courseId": course_id,
            "documentIds": documents,
        }
    )


def test_personal_scope_returns_only_the_selected_own_documents():
    assert search(personal([DOC_ALICE])) == {DOC_ALICE}
    assert search(personal([DOC_ALICE, DOC_ALICE_2])) == {DOC_ALICE, DOC_ALICE_2}


def test_cannot_retrieve_another_users_personal_chunks():
    assert search(personal([DOC_BOB])) == set()
    assert search(personal([DOC_BOB], owner=BOB, workspace=ALICE_WS)) == set()
    assert search(personal([DOC_ALICE], owner=BOB, workspace=BOB_WS)) == set()


def test_owner_in_the_wrong_workspace_gets_nothing():
    assert search(personal([DOC_ALICE], workspace=BOB_WS)) == set()


def test_course_scope_returns_only_its_selected_course_documents():
    assert search(course([DOC_C1])) == {DOC_C1}


def test_cannot_retrieve_a_course_the_user_is_not_in():
    assert search(course([DOC_B])) == set()  # same course id, other classroom
    assert search(course([DOC_C2])) == set()  # same classroom, other course
    assert search(course([DOC_C1], classroom=CLASSROOM_B)) == set()


def test_no_personal_sources_inside_a_course_workspace():
    assert search(course([DOC_ALICE, DOC_BOB])) == set()


def test_no_course_documents_inside_a_personal_workspace():
    assert search(personal([DOC_C1, DOC_C2, DOC_B])) == set()


def test_a_document_outside_the_selection_is_not_returned():
    # The course also holds DOC_C1_OTHER, but the scope doesn't name it.
    assert DOC_C1_OTHER not in search(course([DOC_C1]))


def test_stale_selection_after_leaving_the_classroom_returns_nothing():
    assert search(course([DOC_C1], classroom=uuid4())) == set()


def test_filter_never_widens_the_document_list():
    assert scope_filter(course([DOC_C1])).document_ids == frozenset({DOC_C1})


def test_unknown_scope_is_an_error_not_an_open_filter():
    with pytest.raises(TypeError):
        scope_filter(object())  # type: ignore[arg-type]
