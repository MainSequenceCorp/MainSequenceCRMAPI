"""Expose the existing CRM schemas, diagnostics, and owner operations unchanged."""

import json

from api.erp.crm.mcp_server import crm_runtime_for
from api.erp.crm.mcp_tools import build_crm_tools

from ..admission import active_scope
from ..registry import SKILLS_ROOT, CRMTool

READ = "crm.read"
EDIT = "crm.edit"
CREATE = "crm.create"
IMPORT = "crm.transfer.import"

# The owner continues to enforce input- and record-specific permissions.
_CAPABILITIES = {
    "crm_affiliations_create": (EDIT,),
    "crm_contacts_merge_preview": ("crm.merge",),
    "crm_settings_update": ("crm.configure",),
    "crm_email_messages_create": (READ, CREATE),
    "crm_email_messages_follow_up": (READ, EDIT),
    "crm_gmail_email_search": (READ, IMPORT),
    "crm_gmail_email_preview": (READ, IMPORT),
    "crm_gmail_conversation_preview": (READ, IMPORT),
    "crm_gmail_email_import": (READ, IMPORT, CREATE),
    "crm_gmail_conversation_import": (READ, IMPORT, CREATE),
    "crm_email_thread_set_sync": (READ, EDIT),
    "crm_email_thread_sync": (READ, IMPORT, CREATE, EDIT),
    "crm_outreach_sequences_tasks_advance": (CREATE, EDIT),
}


def _runtime():
    scope = active_scope.get()
    return crm_runtime_for(scope.request, verified_mode=scope.identity_mode)


def register_tools(registry):
    tool_map = SKILLS_ROOT / "crm/crm-core/references/tool-map.json"
    skills = {
        name: f"crm/{skill}"
        for skill, names in json.loads(tool_map.read_text(encoding="utf-8"))["skills"].items()
        for name in names
    }
    for existing in build_crm_tools(_runtime):
        definition = existing.definition
        name = definition.name
        read_only = definition.annotations.read_only_hint
        default = READ if read_only else CREATE if name.endswith("_create") else EDIT
        choices = (_CAPABILITIES.get(name, (default,)),)
        if name == "crm_outreach_sequences_prompts_create":
            choices = ((CREATE,), (EDIT,))
        registry.add(
            CRMTool(
                definition=definition,
                owner_module="crm",
                owner_capabilities=tuple(frozenset(required) for required in choices),
                skill_path=skills[name],
                kind="read" if read_only else "write",
                invoke=existing.invoke,
            )
        )
