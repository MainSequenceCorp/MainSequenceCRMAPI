"""Register explicit ERP tools without deriving actions from client input."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp.types import Tool, ToolAnnotations
from pydantic import BaseModel, TypeAdapter

from src.erp.modules import MODULES

from .contracts import Failure, Success

SKILLS_ROOT = Path(__file__).resolve().parents[3] / ".tau" / "skills"


@dataclass(frozen=True, kw_only=True)
class Entry:
    definition: Tool
    owner_module: str
    owner_capabilities: tuple[frozenset[str], ...]
    skill_path: str
    kind: str
    required_modules: frozenset[str] = frozenset()
    local_only: bool = False
    organization_admin: bool = False
    available: Callable[..., bool] | None = None


@dataclass(frozen=True, kw_only=True)
class ERPTool(Entry):
    input_model: type[BaseModel]
    result_model: type[BaseModel]
    handler: Callable[..., Any]


@dataclass(frozen=True, kw_only=True)
class CRMTool(Entry):
    invoke: Callable[..., Any]


class Registry:
    def __init__(self, module_apps):
        self.module_apps = module_apps
        self.entries: dict[str, ERPTool | CRMTool] = {}

    def add(self, entry: ERPTool | CRMTool) -> None:
        name = entry.definition.name
        if name in self.entries:
            raise ValueError(f"Duplicate ERP tool: {name}")
        if entry.owner_module not in {*MODULES, "user_preferences"}:
            raise ValueError(f"Unknown ERP tool owner: {entry.owner_module}")
        if entry.required_modules - MODULES.keys():
            raise ValueError(f"Unknown module dependency for {name}")
        if not (SKILLS_ROOT / entry.skill_path / "SKILL.md").is_file():
            raise ValueError(f"Missing primary skill for {name}: {entry.skill_path}")
        self.entries[name] = entry

    def read(self, name, **options):
        self.operation(name, kind="read", **options)

    def operation(
        self,
        name,
        *,
        description,
        owner,
        capabilities,
        skill,
        inputs,
        output,
        handler,
        kind,
        required_modules=(),
        local_only=False,
        organization_admin=False,
        available=None,
    ):
        self.add(
            ERPTool(
                definition=Tool(
                    name=name,
                    description=description,
                    inputSchema=inputs.model_json_schema(),
                    outputSchema={
                        "type": "object",
                        **TypeAdapter(Success[output] | Failure).json_schema(),
                    },
                    annotations=ToolAnnotations(
                        readOnlyHint=kind == "read",
                        destructiveHint=kind == "write",
                        idempotentHint=kind == "read",
                        openWorldHint=False,
                    ),
                    _meta={"mainsequence.ai/timeout-seconds/v1": 60},
                ),
                owner_module=owner,
                owner_capabilities=(frozenset(capabilities),) if capabilities else (),
                skill_path=skill,
                kind=kind,
                required_modules=frozenset(required_modules),
                local_only=local_only,
                organization_admin=organization_admin,
                available=available,
                input_model=inputs,
                result_model=output,
                handler=handler,
            )
        )


def register_reads(registry, *, owner, skill, service, resources):
    """Register list/get tools with fixed resource names and the owner's projections."""
    from .contracts import Collection, GetInput, Record

    for resource, label, input_model in resources:
        prefix = f"{owner}_{resource.replace('-', '_')}"
        registry.read(
            f"{prefix}_list",
            description=f"List {label} with bounded filters and pagination.",
            owner=owner,
            capabilities=(f"{owner}.read",),
            skill=skill,
            inputs=input_model,
            output=Collection,
            handler=lambda scope, args, resource=resource: service(scope).collection(
                resource, **args.model_dump()
            ),
        )
        registry.read(
            f"{prefix}_get",
            description=f"Read one record from {label} by UID.",
            owner=owner,
            capabilities=(f"{owner}.read",),
            skill=skill,
            inputs=GetInput,
            output=Record,
            handler=lambda scope, args, resource=resource: service(scope).get(resource, args.uid),
        )
