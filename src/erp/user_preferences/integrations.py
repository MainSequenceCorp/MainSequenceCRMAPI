"""ERP-owned connector workflow definitions and Settings projections."""

from dataclasses import dataclass
from uuid import UUID

from src.erp.modules import REQUIRED_MODULES, module_closure

from .errors import UserPreferencesError
from .schemas import WorkflowSettings

# Preserve the public Settings and GoogleConnector protocol keys already in use.
GOOGLE_CONTACTS = "crm.google-contacts"
GOOGLE_GMAIL = "crm.google-gmail"
GOOGLE_CALENDAR = "crm.google-calendar"
GOOGLE_KEY = "google-workspace"
GOOGLE_CONTACTS_PERMISSIONS = frozenset({"crm.read", "crm.transfer.import"})

# Retained for the one-time migration and local transport, not hosted routing.
INSTALLATION_SETTING = "ERP_GOOGLE_CONTACTS_INSTALLATION_UID"
RELEASE_SETTING = "ERP_GOOGLE_CONTACTS_CONNECTOR_RELEASE_UID"
LOCAL_TOKEN_SETTING = "ERP_GOOGLE_CONTACTS_LOCAL_TOKEN"
LOCAL_TOKEN_HEADER = "X-ERP-Connector-Local-Token"


@dataclass(frozen=True)
class Workflow:
    key: str
    module: str
    title: str
    capability: str
    manifest_capabilities: tuple[str, ...]
    permissions: frozenset[str]
    contract: str = "erp.connector@v1"
    legacy_google_key: str | None = None

    def binding_key(self, connector_key):
        if connector_key == GOOGLE_KEY and self.legacy_google_key:
            return self.legacy_google_key
        return f"{connector_key}.{self.key}"


WORKFLOWS = {
    workflow.key: workflow for workflow in (
        Workflow(
            "finance.bank-reconciliation", "finance", "Bank reconciliation", "banking.transactions",
            ("banking.transactions",), frozenset({"finance.read"}),
        ),
        Workflow(
            "crm.contacts-import", "crm", "Contacts import", "people.contacts",
            ("people.contacts",), GOOGLE_CONTACTS_PERMISSIONS, legacy_google_key=GOOGLE_CONTACTS,
        ),
        Workflow(
            "crm.calendar-import", "crm", "Calendar import", "calendar.events",
            ("calendar.events",), GOOGLE_CONTACTS_PERMISSIONS, legacy_google_key=GOOGLE_CALENDAR,
        ),
        Workflow(
            "crm.gmail-review-and-sync", "crm", "Gmail review and sync", "gmail.mail",
            ("gmail.correspondents", "gmail.messages"), GOOGLE_CONTACTS_PERMISSIONS,
            legacy_google_key=GOOGLE_GMAIL,
        ),
    )
}
GOOGLE_TITLES = {
    GOOGLE_CONTACTS: "Google Contacts",
    GOOGLE_CALENDAR: "Google Calendar",
    GOOGLE_GMAIL: "Gmail",
}


class Binding(WorkflowSettings):
    key: str
    connector_key: str
    workflow_key: str
    release_uid: UUID
    workload_uid: UUID | None
    installation_uid: UUID
    generation: int

    @property
    def workflow(self):
        return WORKFLOWS[self.workflow_key]

    @property
    def title(self):
        return GOOGLE_TITLES.get(self.key, f"{self.connector_key} · {self.workflow.title}")


def known_binding(bindings, key):
    binding = bindings.get(key)
    if binding is None:
        raise UserPreferencesError(404, "integration_not_found", "Unknown ERP integration")
    return binding


def integration_provisioned(binding, provisioned):
    return module_closure((binding.workflow.module,)) <= provisioned


def integration_overview(policy, bindings, provisioned, *, may_use, can_manage):
    active_modules = frozenset(policy["active_module_keys"]) | REQUIRED_MODULES
    active_integrations = frozenset(policy["active_integration_keys"])
    return {
        "policy_version": policy["version"],
        "registry_revision": policy["connector_registry_revision"],
        "can_manage": can_manage,
        "integrations": [
            {
                "key": binding.key,
                "title": binding.title,
                "connector_key": binding.connector_key,
                "workflow_key": binding.workflow_key,
                "module_key": binding.workflow.module,
                "capability": binding.workflow.capability,
                "provisioned": integration_provisioned(binding, provisioned),
                "active": binding.key in active_integrations,
                "admin_only": binding.admin_only,
                "placement": binding.placement,
                "binding_generation": binding.generation,
                "can_access": (
                    (not binding.admin_only or can_manage)
                    and binding.key in active_integrations
                    and module_closure((binding.workflow.module,)) <= active_modules & provisioned
                    and may_use(binding.workflow)
                ),
                "connector_release_uid": binding.release_uid,
            }
            for binding in bindings.values()
        ],
    }
