"""Scope built by Spring Boot (contracts/ai-service.yaml#/components/schemas/Scope).

Every vector or keyword search takes a Scope and filters by it. This service never widens it.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

# Unknown fields are ignored (contract: "Unknown properties are ignored"), so a newer backend keeps
# working. Fields of the *other* scope type are not unknown: they mean the caller mixed up the
# scope, so they are rejected instead of being silently dropped.
_COURSE_FIELDS = frozenset({"classroomId", "classroom_id", "courseId", "course_id"})
_PERSONAL_FIELDS = frozenset({"workspaceId", "workspace_id", "ownerId", "owner_id"})


def _reject_foreign_fields(data: object, foreign: frozenset[str]) -> object:
    if isinstance(data, dict) and (clash := foreign & data.keys()):
        raise ValueError(f"fields of another scope type: {sorted(clash)}")
    return data


class _ScopeBase(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, extra="ignore", frozen=True)

    document_ids: Annotated[list[UUID], Field(min_length=1)]


class PersonalScope(_ScopeBase):
    scope_type: Literal["personal"]
    workspace_id: UUID
    owner_id: UUID

    @model_validator(mode="before")
    @classmethod
    def _no_course_fields(cls, data: object) -> object:
        return _reject_foreign_fields(data, _COURSE_FIELDS)


class CourseScope(_ScopeBase):
    scope_type: Literal["course"]
    classroom_id: UUID
    course_id: UUID

    @model_validator(mode="before")
    @classmethod
    def _no_personal_fields(cls, data: object) -> object:
        return _reject_foreign_fields(data, _PERSONAL_FIELDS)


Scope = Annotated[PersonalScope | CourseScope, Field(discriminator="scope_type")]
