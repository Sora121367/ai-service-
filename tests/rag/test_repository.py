"""ChunkRepository. Validation tests always run; the `db` tests need TEST_DATABASE_URL (conftest)."""

from uuid import UUID, uuid4

import pytest

from app.api.scope import CourseScope, IngestCourseScope, IngestPersonalScope, PersonalScope
from app.clients.embeddings import EMBEDDING_DIMENSION
from app.ingestion.chunking import Chunk
from app.ingestion.parsing.models import Anchor
from app.rag.repository import ChunkRepository
from app.rag.scope_filter import scope_filter

ALICE, BOB = uuid4(), uuid4()
ALICE_WS, BOB_WS = uuid4(), uuid4()
CLASSROOM_A, CLASSROOM_B = uuid4(), uuid4()
COURSE_1, COURSE_2 = uuid4(), uuid4()


def unit(position: int) -> list[float]:
    """A one-hot vector, so each document is exactly orthogonal to the others."""
    vector = [0.0] * EMBEDDING_DIMENSION
    vector[position] = 1.0
    return vector


def chunk(index: int = 0, text: str = "some text", **anchor) -> Chunk:
    return Chunk(index=index, text=text, source_type="pdf", anchor=Anchor(**anchor))


def personal_ingest(owner=ALICE, workspace=ALICE_WS) -> IngestPersonalScope:
    return IngestPersonalScope.model_validate(
        {"scopeType": "personal", "ownerId": owner, "workspaceId": workspace}
    )


def course_ingest(classroom=CLASSROOM_A, course=COURSE_1) -> IngestCourseScope:
    return IngestCourseScope.model_validate(
        {"scopeType": "course", "classroomId": classroom, "courseId": course}
    )


def personal_scope(documents, owner=ALICE, workspace=ALICE_WS) -> PersonalScope:
    return PersonalScope.model_validate(
        {
            "scopeType": "personal",
            "ownerId": owner,
            "workspaceId": workspace,
            "documentIds": documents,
        }
    )


def course_scope(documents, classroom=CLASSROOM_A, course=COURSE_1) -> CourseScope:
    return CourseScope.model_validate(
        {
            "scopeType": "course",
            "classroomId": classroom,
            "courseId": course,
            "documentIds": documents,
        }
    )


# --- validation, no database ---------------------------------------------------------------


def test_replace_rejects_a_different_number_of_embeddings_and_chunks():
    with pytest.raises(ValueError, match="1 chunks but 0 embeddings"):
        ChunkRepository(None).replace_document(  # type: ignore[arg-type]
            document_id=uuid4(), scope=personal_ingest(), chunks=[chunk()], embeddings=[]
        )


def test_replace_rejects_a_vector_of_the_wrong_size_before_touching_the_database():
    with pytest.raises(ValueError, match="1024 dimensions"):
        ChunkRepository(None).replace_document(  # type: ignore[arg-type]
            document_id=uuid4(), scope=personal_ingest(), chunks=[chunk()], embeddings=[[0.1, 0.2]]
        )


def test_search_rejects_a_non_positive_limit():
    with pytest.raises(ValueError, match="limit"):
        ChunkRepository(None).search_chunks(  # type: ignore[arg-type]
            personal_scope([uuid4()]), unit(0), limit=0
        )


# --- database ------------------------------------------------------------------------------


@pytest.mark.db
def test_first_ingest_is_version_one_and_stores_the_anchor(repository):
    document = uuid4()

    version = repository.replace_document(
        document_id=document,
        scope=personal_ingest(),
        chunks=[chunk(0, "page text", page=3, section_path=("Intro", "Basics"))],
        embeddings=[unit(0)],
        file_name="notes.pdf",
    )
    (hit,) = repository.search_chunks(personal_scope([document]), unit(0))

    assert version == 1
    assert (hit.text, hit.page, hit.section_path, hit.file_name) == (
        "page text",
        3,
        ("Intro", "Basics"),
        "notes.pdf",
    )
    assert hit.score == pytest.approx(1.0)


@pytest.mark.db
def test_ingesting_again_replaces_the_old_chunks_and_bumps_the_version(repository):
    document = uuid4()
    repository.replace_document(
        document_id=document,
        scope=personal_ingest(),
        chunks=[chunk(0, "old a"), chunk(1, "old b")],
        embeddings=[unit(0), unit(1)],
    )

    version = repository.replace_document(
        document_id=document,
        scope=personal_ingest(),
        chunks=[chunk(0, "new")],
        embeddings=[unit(0)],
    )
    hits = repository.search_chunks(personal_scope([document]), unit(0), limit=10)

    assert version == 2
    assert [hit.text for hit in hits] == ["new"]


@pytest.mark.db
def test_a_failed_replace_keeps_the_old_chunks(repository):
    document = uuid4()
    repository.replace_document(
        document_id=document,
        scope=personal_ingest(),
        chunks=[chunk(0, "keep")],
        embeddings=[unit(0)],
    )

    with pytest.raises(Exception):  # noqa: B017 - a duplicate chunk_index fails mid-transaction
        repository.replace_document(
            document_id=document,
            scope=personal_ingest(),
            chunks=[chunk(0, "x"), chunk(0, "y")],
            embeddings=[unit(0), unit(1)],
        )

    hits = repository.search_chunks(personal_scope([document]), unit(0))
    assert [h.text for h in hits] == ["keep"]


@pytest.mark.db
def test_link_chunks_keep_their_source_url(repository):
    document = uuid4()
    repository.replace_document(
        document_id=document,
        scope=course_ingest(),
        chunks=[chunk(0)],
        embeddings=[unit(0)],
        source_url="https://example.com/a",
    )

    (hit,) = repository.search_chunks(course_scope([document]), unit(0))

    assert hit.source_url == "https://example.com/a"


@pytest.fixture
def corpus(repository):
    """Documents in two personal workspaces and two courses; each has a distinct one-hot vector."""
    docs = {name: uuid4() for name in ("alice", "alice2", "bob", "c1", "c1_other", "c2", "b")}
    layout = [
        ("alice", personal_ingest(ALICE, ALICE_WS)),
        ("alice2", personal_ingest(ALICE, ALICE_WS)),
        ("bob", personal_ingest(BOB, BOB_WS)),
        ("c1", course_ingest(CLASSROOM_A, COURSE_1)),
        ("c1_other", course_ingest(CLASSROOM_A, COURSE_1)),
        ("c2", course_ingest(CLASSROOM_A, COURSE_2)),
        ("b", course_ingest(CLASSROOM_B, COURSE_1)),
    ]
    for position, (name, scope) in enumerate(layout):
        repository.replace_document(
            document_id=docs[name],
            scope=scope,
            chunks=[chunk(0, name)],
            embeddings=[unit(position)],
        )
    return docs


def found(repository, scope) -> set[UUID]:
    """Every document the scope can see: a query close to all of them, with a generous limit."""
    flat = [1.0] * EMBEDDING_DIMENSION
    return {hit.document_id for hit in repository.search_chunks(scope, flat, limit=100)}


@pytest.mark.db
def test_scope_sees_only_its_selected_documents(repository, corpus):
    assert found(repository, personal_scope([corpus["alice"]])) == {corpus["alice"]}
    assert found(repository, personal_scope([corpus["alice"], corpus["alice2"]])) == {
        corpus["alice"],
        corpus["alice2"],
    }
    assert found(repository, course_scope([corpus["c1"]])) == {corpus["c1"]}


@pytest.mark.db
def test_cannot_retrieve_another_users_personal_chunks(repository, corpus):
    bob_doc, alice_doc = corpus["bob"], corpus["alice"]
    assert found(repository, personal_scope([bob_doc])) == set()
    assert found(repository, personal_scope([bob_doc], owner=BOB, workspace=ALICE_WS)) == set()
    assert found(repository, personal_scope([alice_doc], owner=BOB, workspace=BOB_WS)) == set()
    assert found(repository, personal_scope([alice_doc], workspace=BOB_WS)) == set()


@pytest.mark.db
def test_cannot_retrieve_a_course_the_user_is_not_in(repository, corpus):
    assert found(repository, course_scope([corpus["b"]])) == set()
    assert found(repository, course_scope([corpus["c2"]])) == set()
    assert found(repository, course_scope([corpus["c1"]], classroom=CLASSROOM_B)) == set()
    assert found(repository, course_scope([corpus["c1"]], classroom=uuid4())) == set()


@pytest.mark.db
def test_personal_and_course_sources_never_cross(repository, corpus):
    assert found(repository, course_scope([corpus["alice"], corpus["bob"]])) == set()
    assert found(repository, personal_scope([corpus["c1"], corpus["c2"], corpus["b"]])) == set()


@pytest.mark.db
def test_a_document_outside_the_selection_is_not_returned(repository, corpus):
    assert corpus["c1_other"] not in found(repository, course_scope([corpus["c1"]]))


@pytest.mark.db
def test_sql_results_agree_with_the_reference_filter(repository, corpus):
    placement = {
        "alice": ("personal", ALICE_WS, ALICE),
        "alice2": ("personal", ALICE_WS, ALICE),
        "bob": ("personal", BOB_WS, BOB),
        "c1": ("course", CLASSROOM_A, COURSE_1),
        "c1_other": ("course", CLASSROOM_A, COURSE_1),
        "c2": ("course", CLASSROOM_A, COURSE_2),
        "b": ("course", CLASSROOM_B, COURSE_1),
    }

    def metadata(name):
        kind, first, second = placement[name]
        document_id = corpus[name]
        if kind == "personal":
            return {
                "scope_type": kind,
                "workspace_id": first,
                "owner_id": second,
                "document_id": document_id,
            }
        return {
            "scope_type": kind,
            "classroom_id": first,
            "course_id": second,
            "document_id": document_id,
        }

    everything = list(corpus.values())
    scopes = [
        personal_scope(everything),
        personal_scope(everything, owner=BOB, workspace=BOB_WS),
        course_scope(everything),
        course_scope(everything, course=COURSE_2),
        course_scope(everything, classroom=CLASSROOM_B),
    ]
    for scope in scopes:
        expected = {corpus[n] for n in corpus if scope_filter(scope).matches(metadata(n))}
        assert found(repository, scope) == expected


@pytest.mark.db
def test_results_are_nearest_first(repository):
    near, far = uuid4(), uuid4()
    for document, vector in ((near, unit(0)), (far, unit(1))):
        repository.replace_document(
            document_id=document, scope=personal_ingest(), chunks=[chunk(0)], embeddings=[vector]
        )

    hits = repository.search_chunks(personal_scope([near, far]), unit(0))

    assert [hit.document_id for hit in hits] == [near, far]


@pytest.mark.db
def test_delete_document_is_idempotent(repository, corpus):
    assert repository.delete_document(corpus["alice"]) == 1
    assert repository.delete_document(corpus["alice"]) == 0
    assert repository.delete_document(uuid4()) == 0


@pytest.mark.db
def test_delete_workspace_and_owner_touch_only_personal_chunks(repository, corpus):
    assert repository.delete_workspace(ALICE_WS) == 2
    assert repository.delete_workspace(ALICE_WS) == 0
    assert repository.delete_owner(BOB) == 1
    assert repository.delete_owner(BOB) == 0
    assert repository.delete_workspace(CLASSROOM_A) == 0  # an id that is only a classroom
    assert set(repository.list_document_ids()) == {
        corpus[name] for name in ("c1", "c1_other", "c2", "b")
    }


@pytest.mark.db
def test_list_document_ids_pages_in_id_order_and_filters_by_scope_type(repository, corpus):
    everything = sorted(corpus.values())

    first = repository.list_document_ids(limit=3)
    second = repository.list_document_ids(limit=3, after=first[-1])
    third = repository.list_document_ids(limit=3, after=second[-1])

    assert first + second + third == everything
    assert set(repository.list_document_ids(scope_type="course")) == {
        corpus[name] for name in ("c1", "c1_other", "c2", "b")
    }
    assert set(repository.list_document_ids(scope_type="personal")) == {
        corpus[name] for name in ("alice", "alice2", "bob")
    }
