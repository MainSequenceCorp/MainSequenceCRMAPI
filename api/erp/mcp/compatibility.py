"""Serve cached CRM MCP names during the ERP catalogue cutover."""

from dataclasses import replace
from pathlib import Path

from mcp.server.extension import Extension

from mainsequence.server.mcp_skills import skills_extension

_OUTREACH_TOOLS = {
    "crm_campaigns_": ("list", "get", "create", "update", "graph_validate", "graph_update"),
    "crm_campaign_prompts_": ("list", "get", "create", "update"),
    "crm_campaign_participants_": ("list", "get", "create", "update"),
    "crm_campaign_tasks_": (
        "prepare",
        "advance",
        "complete",
        "wait",
        "block",
        "report",
        "reconcile",
    ),
}

CRM_TOOL_ALIASES = {
    old_prefix + operation: "crm_outreach_sequences_" + family + operation
    for old_prefix, family in (
        ("crm_campaigns_", ""),
        ("crm_campaign_prompts_", "prompts_"),
        ("crm_campaign_participants_", "participants_"),
        ("crm_campaign_tasks_", "tasks_"),
    )
    for operation in _OUTREACH_TOOLS[old_prefix]
}


class ERPSkills(Extension):
    """Keep direct reads of previously published URIs during consumer migration."""

    identifier = "io.modelcontextprotocol/skills"

    def __init__(self, directory):
        self.current = skills_extension(directory)
        self.legacy = skills_extension(Path(__file__).with_name("legacy_crm_skills"))
        self.legacy_entries = frozenset(
            str(binding.resource.uri)
            for binding in self.legacy.resources()
            if str(binding.resource.uri).endswith("/SKILL.md")
        )

    def settings(self):
        return self.current.settings()

    def resources(self):
        return [*self.current.resources(), *self.legacy.resources()]

    def methods(self):
        current = {binding.method: binding for binding in self.current.methods()}
        current_get = current["skills/get"]
        legacy_get = next(
            binding for binding in self.legacy.methods() if binding.method == "skills/get"
        )

        async def lookup(ctx, params):
            handler = (
                legacy_get.handler if params.uri in self.legacy_entries else current_get.handler
            )
            return await handler(ctx, params)

        return [
            *(binding for method, binding in current.items() if method != "skills/get"),
            replace(current_get, handler=lookup),
        ]
