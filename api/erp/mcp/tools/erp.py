"""The caller's ERP module availability and prerequisites."""

from pydantic import BaseModel, Field, JsonValue, field_validator

from api.erp.user_preferences.main import module_overview
from src.erp.modules import MODULES

from ..contracts import EmptyInput


class ModuleAvailability(BaseModel):
    key: str
    title: str
    provisioned: bool
    active: bool
    can_access: bool
    prerequisites: tuple[str, ...]


class Availability(BaseModel):
    modules: list[ModuleAvailability]
    policy_version: int


class CatalogueInput(EmptyInput):
    module: str
    name: str | None = Field(default=None, min_length=1, max_length=128)
    offset: int = Field(default=0, ge=0, le=1000, strict=True)
    limit: int = Field(default=6, ge=1, le=10, strict=True)

    @field_validator("module")
    @classmethod
    def known_module(cls, value):
        if value not in {*MODULES, "erp", "settings"}:
            raise ValueError("Unknown ERP module")
        return value


class ToolInput(BaseModel):
    name: str
    description: str
    input_schema: dict[str, JsonValue]


class Catalogue(BaseModel):
    tools: list[ToolInput]
    next_offset: int | None


def _describe(registry, scope, args):
    visible = []
    for name, entry in sorted(registry.entries.items()):
        if entry.skill_path.split("/", 1)[0] != args.module or args.name and args.name != name:
            continue
        try:
            scope.admit(entry)
        except Exception:
            continue
        definition = entry.definition
        visible.append(
            {
                "name": name,
                "description": definition.description,
                "input_schema": definition.input_schema,
            }
        )
    end = args.offset + args.limit
    return {
        "tools": visible[args.offset : end],
        "next_offset": end if end < len(visible) else None,
    }


def register_tools(registry):
    registry.read(
        "erp_modules_list",
        description="Read module availability and prerequisites for this ERP Environment.",
        owner="user_preferences",
        capabilities=(),
        skill="erp/erp-workflows",
        inputs=EmptyInput,
        output=Availability,
        handler=lambda scope, _: module_overview(
            scope.settings, local=scope.local, policy=scope.policy
        ),
    )

    registry.read(
        "erp_tools_describe",
        description="Read bounded input schemas for the currently permitted tools of one ERP module.",
        owner="user_preferences",
        capabilities=(),
        skill="erp/erp-workflows",
        inputs=CatalogueInput,
        output=Catalogue,
        handler=lambda scope, args: _describe(registry, scope, args),
    )
