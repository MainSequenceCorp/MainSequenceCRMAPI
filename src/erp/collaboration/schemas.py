"""Strict discussion contracts; scope and verified authors cannot be forged."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]
Version = Annotated[int, Field(strict=True, ge=1)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VersionInput(Input):
    expected_version: Version


class DiscussionInput(Input):
    name: Name
    description: str = Field(default="", max_length=2000)


class DiscussionCreate(DiscussionInput):
    request_uid: UUID
    scope: Literal["shared", "project"]
    project_uid: UUID | None = None
    audience: Literal["collaboration_readers", "authorized_project_readers"]

    @model_validator(mode="after")
    def audience_matches(self):
        if (self.scope == "project") != bool(self.project_uid) or self.audience != (
            "authorized_project_readers" if self.scope == "project" else "collaboration_readers"
        ):
            raise ValueError("Acknowledge the exact audience matching this discussion's scope")
        return self


class DiscussionUpdate(DiscussionInput, VersionInput):
    pass


class MessageCreate(Input):
    request_uid: UUID
    expected_discussion_version: Version
    body: Text


class MessageEdit(VersionInput):
    expected_discussion_version: Version
    body: Text


class MessageRetract(VersionInput):
    expected_discussion_version: Version
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
