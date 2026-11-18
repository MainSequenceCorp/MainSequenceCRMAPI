"""Strict application-owned write contracts for ERP settings."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.erp.modules import OPTIONAL_MODULES


def optional_keys(keys):
    if len(set(keys)) != len(keys):
        raise ValueError("Module keys must be unique")
    if set(keys) - OPTIONAL_MODULES:
        raise ValueError("Only registered optional ERP module keys are accepted")
    return sorted(keys)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PreferenceInput(Input):
    expected_version: int = Field(ge=0, strict=True)
    hidden_module_keys: list[str] = Field(max_length=len(OPTIONAL_MODULES))

    @field_validator("hidden_module_keys")
    @classmethod
    def valid_keys(cls, keys):
        return optional_keys(keys)


class ActivationProposal(Input):
    expected_version: int = Field(ge=0, strict=True)
    active_module_keys: list[str] = Field(max_length=len(OPTIONAL_MODULES))

    @field_validator("active_module_keys")
    @classmethod
    def valid_keys(cls, keys):
        return optional_keys(keys)


class ActivationInput(ActivationProposal):
    request_uid: UUID
