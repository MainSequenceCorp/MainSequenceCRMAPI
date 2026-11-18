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


admission: ContextVar[Admission | None] = ContextVar("erp_module_admission", default=None)


def require_module(module_key: str) -> None:
    current = admission.get()
    if current is not None:
        current.require(module_key)


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
