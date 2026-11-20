"""Strict application-owned write contracts for ERP settings."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


class IntegrationActivationInput(Input):
    active: bool = Field(strict=True)
    expected_version: int = Field(ge=1, strict=True)
    request_uid: UUID


class IntegrationAdmissionInput(Input):
    actor_uid: UUID
    operation: Literal["read", "configure"] = "read"


class WorkflowSettings(Input):
    admin_only: bool = Field(default=False, strict=True)
    placement: Literal["connector_menu", "module_menu", "settings"] | None = None

    @model_validator(mode="after")
    def settings_requires_admin(self):
        if self.placement == "settings" and not self.admin_only:
            raise ValueError("Settings placement requires admin_only: true")
        return self


class ConnectorEntry(Input):
    release_uid: UUID
    workflows: list[str] = Field(min_length=1, max_length=32)

    workflow_settings: dict[str, WorkflowSettings] = Field(default_factory=dict, max_length=32)

    @model_validator(mode="after")
    def selected_workflow_settings(self):
        if self.workflow_settings.keys() - set(self.workflows):
            raise ValueError("Workflow settings must refer to a listed workflow")
        return self

    @field_validator("workflows")
    @classmethod
    def unique_workflows(cls, workflows):
        if len(set(workflows)) != len(workflows):
            raise ValueError("Connector workflow keys must be unique")
        return workflows


class ConnectorRegistryDocument(Input):
    schema_version: int = Field(strict=True, ge=1, le=2)
    environment_uid: UUID
    connectors: dict[str, ConnectorEntry] = Field(max_length=256)


    @model_validator(mode="after")
    def workflow_settings_version(self):
        if self.schema_version == 1 and any(
            "workflow_settings" in entry.model_fields_set for entry in self.connectors.values()
        ):
            raise ValueError("Workflow settings require registry schema version 2")
        return self


class ConnectorRegistryPublication(Input):
    expected_revision: int = Field(ge=0, strict=True)
    yaml: str = Field(min_length=1, max_length=65536)
