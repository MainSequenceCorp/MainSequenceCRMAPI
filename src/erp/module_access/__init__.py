"""Server-side module admission shared by HTTP, owner ports and transactions."""

from contextvars import ContextVar
from dataclasses import dataclass, field
from uuid import UUID

from metatables import MetaTable, MetaTableTransactionGuardError
from src.erp.modules import module_closure
from src.erp.user_preferences.errors import UserPreferencesError


@dataclass
class Admission:
    scope: UUID
    local: bool
    version: int
    active: frozenset[str]
    used: set[str] = field(default_factory=set)

    def require(self, module_key: str) -> None:
        required = module_closure((module_key,))
        if required - self.active:
            raise UserPreferencesError(403, "module_disabled", "This ERP module is inactive.")
        self.used.update(required)


def admission_for(scope, *, local, policy, provisioned) -> Admission:
    from src.erp.modules import REQUIRED_MODULES

    active = (frozenset(policy["active_module_keys"]) | REQUIRED_MODULES) & provisioned
    return Admission(scope, local, policy["version"], active)


admission: ContextVar[Admission | None] = ContextVar("erp_module_admission", default=None)


def require_module(module_key: str) -> None:
    current = admission.get()
    if current is not None:
        current.require(module_key)


def require_integration(key: str) -> dict:
    """Require the selected provider workflow inside a version-pinned business request."""
    current = admission.get()
    if current is None:
        raise UserPreferencesError(
            503, "module_policy_unavailable", "ERP integration admission is unavailable"
        )
    from src.erp.user_preferences.admission import require_integration as check_policy

    from src.erp.user_preferences.identity import request_person, require_workflow_admin

    policy = check_policy(current.scope, key, local=current.local)
    binding = policy["connector_binding"]
    current.require(binding.workflow.module)
    require_workflow_admin(binding, lambda: request_person(local=current.local))
    if policy["version"] != current.version:
        raise UserPreferencesError(
            409, "module_policy_changed", "Module policy changed. Reload before retrying."
        )
    return policy


def module_available(module_key: str) -> bool:
    current = admission.get()
    return current is None or module_closure((module_key,)) <= current.active


def admitted_guards(module_key, source_uid):
    current = admission.get()
    if current is None:
        # Domain fixtures, offline migrations and Base integrity composition do
        # not enter the optional module business API.
        return []
    from src.erp.user_preferences.admission import guard_active

    current.require(module_key)
    return guard_active(
        current.scope,
        tuple(sorted(current.used)),
        source_uid,
        local=current.local,
        policy_version=current.version,
    )


def guard_write(module_key, source_uid, statements):
    return [*admitted_guards(module_key, source_uid), *statements]


def execute_write(transaction):
    try:
        return MetaTable.execute_transaction(transaction)
    except MetaTableTransactionGuardError as exc:
        if exc.label in {"erp_module_admission_lock", "erp_module_policy_version"}:
            raise UserPreferencesError(
                409, "module_policy_changed", "Module policy changed. Reload before retrying."
            ) from exc
        raise
