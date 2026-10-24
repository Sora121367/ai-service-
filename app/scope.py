"""Scope built by Spring Boot (contracts/ai-service.yaml#/components/schemas/Scope).

Every vector or keyword search takes a Scope and filters by it. This service never widens it.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _ScopeBase(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, extra="forbid", frozen=True)

    document_ids: Annotated[list[UUID], Field(min_length=1)]


class PersonalScope(_ScopeBase):
    scope_type: Literal["personal"]
    workspace_id: UUID
    owner_id: UUID


class CourseScope(_ScopeBase):
    scope_type: Literal["course"]
    classroom_id: UUID
    course_id: UUID


Scope = Annotated[PersonalScope | CourseScope, Field(discriminator="scope_type")]
