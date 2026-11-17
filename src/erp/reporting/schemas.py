"""Typed report choices and version-fenced operations; no SQL or executable expressions."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Version = Annotated[int, Field(ge=1, strict=True)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DefinitionInput(Input):
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["commercial", "operations"] = "commercial"
    search: str = Field(default="", max_length=120)


class DefinitionCreate(DefinitionInput):
    request_uid: UUID


class DefinitionUpdate(DefinitionInput):
    expected_version: Version


class VersionInput(Input):
    expected_version: Version


class RunCreate(Input):
    request_uid: UUID
    definition_uid: UUID
    expected_definition_version: Version


class ScheduleInput(Input):
    name: str = Field(min_length=1, max_length=200)
    definition_uid: UUID
    interval_minutes: Annotated[int, Field(ge=1, le=1440, strict=True)]


class ScheduleCreate(ScheduleInput):
    request_uid: UUID


class ScheduleUpdate(ScheduleInput):
    expected_version: Version
