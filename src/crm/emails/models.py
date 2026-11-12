"""Strict email contracts. Provider provenance is assigned only by the server."""

from datetime import timedelta
from typing import Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Address(StrictModel):
    email: EmailStr
    name: str | None = Field(default=None, max_length=255)


class MessageFields(StrictModel):
    sender: Address
    to: list[Address] = Field(default_factory=list, max_length=100)
    cc: list[Address] = Field(default_factory=list, max_length=100)
    subject: str = Field(max_length=2000)
    sent_at: AwareDatetime | None = None
    body_text: str = Field(max_length=100000)
    body_state: Literal["complete", "unavailable"] = "complete"
    original_url: str | None = Field(default=None, max_length=2048)

    @field_validator("subject", "body_text")
    @classmethod
    def no_nul(cls, value):
        if "\0" in value:
            raise ValueError("Email text contains NUL")
        return value

    @field_validator("original_url")
    @classmethod
    def safe_url(cls, value):
        if value is not None:
            from urllib.parse import urlsplit
            url = urlsplit(value)
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError("Use an HTTPS source link without credentials")
        return value


class EmailContext(StrictModel):
    contact_uid: UUID
    company_uid: UUID | None = None
    deal_uid: UUID | None = None
    interaction_uid: UUID | None = None
    lead_uid: UUID | None = None
    expected_lead_version: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode="after")
    def lead_version(self):
        if bool(self.lead_uid) != (self.expected_lead_version is not None):
            raise ValueError("Linking a Lead requires its current version")
        return self


class ManualEmailCreate(EmailContext, MessageFields):
    pass


class EmailFilters(StrictModel):
    contact_uid: UUID | None = None
    company_uid: UUID | None = None
    deal_uid: UUID | None = None
    interaction_uid: UUID | None = None
    thread_uid: UUID | None = None
    lead_uid: UUID | None = None


class EmailQuery(StrictModel):
    page_index: int = Field(default=0, ge=0, strict=True)
    page_size: int = Field(default=25, ge=1, le=100, strict=True)
    search: str | None = Field(default=None, max_length=255)
    filters: EmailFilters = Field(default_factory=EmailFilters)
    ordering: Literal["sent_at", "-sent_at", "subject", "-subject"] = "-sent_at"


class GmailSearch(StrictModel):
    query: str = Field(min_length=1, max_length=200)
    time_min: AwareDatetime
    time_max: AwareDatetime
    page_token: str | None = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def bounded(self):
        if self.time_max <= self.time_min or self.time_max - self.time_min > timedelta(days=90):
            raise ValueError("Choose a date range of at most 90 days")
        return self


class GmailPreview(StrictModel):
    message_id: str = Field(min_length=1, max_length=256, pattern=r"^[a-zA-Z0-9_-]+$")


class GmailMessagePreview(EmailContext, GmailPreview):
    pass


class GmailImport(EmailContext):
    preview_token: str = Field(min_length=32, max_length=16000)
    audience: Literal["shared_crm_readers"]


class GmailConversationPreview(EmailContext):
    message_id: str = Field(min_length=1, max_length=256, pattern=r"^[a-zA-Z0-9_-]+$")
    offset: int = Field(default=0, ge=0, le=1000, strict=True)


class GmailConversationImport(EmailContext):
    review_token: str = Field(min_length=32, max_length=24000)
    message_ids: list[str] = Field(min_length=1, max_length=25)
    audience: Literal["shared_crm_readers"]

    @field_validator("message_ids")
    @classmethod
    def unique_ids(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Select each message once")
        for identifier in value:
            GmailPreview(message_id=identifier)
        return value


class SyncChoice(StrictModel):
    expected_version: int = Field(ge=1, strict=True)
    enabled: StrictBool


class FollowUp(StrictModel):
    text: str = Field(default="Follow up on email", min_length=1, max_length=100000)
    due_at: AwareDatetime | None = None
    owner_uid: UUID | None = None
    existing_task_uid: UUID | None = None
    expected_task_version: int | None = Field(default=None, ge=1, strict=True)
    lead_uid: UUID | None = None
    expected_lead_version: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode="after")
    def versions(self):
        if bool(self.existing_task_uid) != (self.expected_task_version is not None):
            raise ValueError("Reusing a Task requires its version")
        if bool(self.lead_uid) != (self.expected_lead_version is not None):
            raise ValueError("Linking a Lead requires its version")
        return self
