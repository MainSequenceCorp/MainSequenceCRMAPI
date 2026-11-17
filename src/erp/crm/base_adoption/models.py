"""Additive HTTP command for explicit Directory-to-CRM adoption."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AdoptParty(BaseModel):
    model_config = ConfigDict(extra="forbid")
    party_uid: UUID
    expected_party_version: int = Field(ge=1, strict=True)
