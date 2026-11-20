"""Assistant discovery metadata shared by ERP and CRM startup."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, constr


class LocalRuntime(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["local"]
    base_path: Literal["/tau"]


class PlatformRuntime(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["platform"]


class AssistantUnavailable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: Literal[False]
    runtime: None
    agent_uid: None
    environment_uid: None
    display_name: str | None


class AssistantLocal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: Literal[True]
    runtime: LocalRuntime
    agent_uid: None
    environment_uid: None
    display_name: constr(min_length=1)


class AssistantPlatform(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: Literal[True]
    runtime: PlatformRuntime
    agent_uid: UUID
    environment_uid: UUID
    display_name: constr(min_length=1)


AssistantMetadata = AssistantUnavailable | AssistantLocal | AssistantPlatform
