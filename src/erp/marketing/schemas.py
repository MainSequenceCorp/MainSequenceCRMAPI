"""Strict Marketing commands keep actor, mode and result fields server-owned."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StrictBool, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]
Evidence = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Version = Annotated[int, Field(strict=True, ge=1)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class VersionInput(Input):
    expected_version: Version


class SubscriberCreate(Input):
    request_uid: UUID
    party_uid: UUID
    email: EmailStr
    evidence: Evidence


class SubscriptionChange(VersionInput):
    state: Literal["subscribed", "unsubscribed"]
    evidence: Evidence


class MailingInput(Input):
    name: Name
    subject: Name
    body: Text
    sender_email: EmailStr
    source_label: str = Field(default="", max_length=200)


class MailingCreate(MailingInput):
    request_uid: UUID


class MailingUpdate(MailingInput, VersionInput):
    pass


class RecipientCreate(VersionInput):
    request_uid: UUID
    subscriber_uid: UUID


class RecipientChange(VersionInput):
    expected_mailing_version: Version


class QueueInput(VersionInput):
    acknowledge_local_capture: StrictBool


class SimulationInput(RecipientChange):
    kind: Literal["opened", "clicked", "replied", "bounced"]
    evidence: Evidence


class FollowupInput(RecipientChange):
    task_uid: UUID
