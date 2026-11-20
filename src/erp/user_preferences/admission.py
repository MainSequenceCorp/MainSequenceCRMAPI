"""Shared Environment activation checks and guarded admission statements."""

from uuid import UUID

from sqlalchemy import select, update

from metatables.compiled_sql.v1 import GuardedStatement
from src.erp.modules import (
    MODULES,
    OPTIONAL_MODULES,
    REQUIRED_MODULES,
    active_modules,
    module_closure,
)

from .connector_registry import read_bindings
from .errors import UserPreferencesError
from .integrations import known_binding
from .metatables import EnvironmentModuleActivation, ModuleAdmissionLock
from .scope import provisioned_module_keys, require_local_runtime
from .store import configured_store

LOCK_LABEL = "erp_module_admission_lock"
POLICY_LABEL = "erp_module_policy_version"


def read_policy(store, scope, *, allow_uninitialized=False, include_integrations=False):
    model = EnvironmentModuleActivation.__table__
    columns = (model.c.version, model.c.active_module_keys)
    if include_integrations:
        columns += (model.c.active_integration_keys, model.c.connector_registry_revision)
    row = store.one(select(*columns).where(model.c.environment_uid == UUID(str(scope))))
    if row is None:
        if allow_uninitialized:
            return None
        raise UserPreferencesError(
            503, "module_policy_unavailable", "ERP module activation has not been initialized"
        )
    keys = row["active_module_keys"]
    if (
        not isinstance(keys, list)
        or not all(isinstance(key, str) and key in OPTIONAL_MODULES for key in keys)
        or len(keys) != len(set(keys))
        or not isinstance(row["version"], int)
        or row["version"] < 1
    ):
        raise UserPreferencesError(
            503, "module_policy_unavailable", "Stored ERP module activation is invalid"
        )
    try:
        active_modules(keys)
    except ValueError as exc:
        raise UserPreferencesError(
            503, "module_policy_unavailable", "Stored ERP module prerequisites are invalid"
        ) from exc
    if include_integrations:
        integrations = row["active_integration_keys"]
        if (
            not isinstance(integrations, list)
            or not all(isinstance(key, str) and 0 < len(key) <= 128 for key in integrations)
            or type(row["connector_registry_revision"]) is not int
            or row["connector_registry_revision"] < 0
            or len(integrations) != len(set(integrations))
        ):
            raise UserPreferencesError(
                503, "module_policy_unavailable", "Stored ERP integration activation is invalid"
            )
    return row


def require_active(scope, module_keys, *, local=False, include_integrations=False):
    keys = frozenset(module_keys)
    if keys - MODULES.keys():
        raise UserPreferencesError(503, "module_policy_unavailable", "Unknown module admission key")
    required = module_closure(keys)
    policy = read_policy(
        configured_store(local=local, policy_only=True),
        scope,
        include_integrations=include_integrations,
    )
    effective = (
        frozenset(policy["active_module_keys"]) | REQUIRED_MODULES
    ) & provisioned_module_keys()
    if required - effective:
        raise UserPreferencesError(403, "module_disabled", "A required ERP module is inactive")
    return policy



def integration_snapshot(scope, *, local=False):
    store = configured_store(local=local, policy_only=True)
    policy = read_policy(store, scope, include_integrations=True)
    return policy, read_bindings(store, scope, policy["connector_registry_revision"])


def require_integration(scope, key, *, local=False):
    """Admit one registered workflow and pin it to the shared policy version."""
    policy, bindings = integration_snapshot(scope, local=local)
    binding = known_binding(bindings, key)
    effective = (frozenset(policy["active_module_keys"]) | REQUIRED_MODULES) & provisioned_module_keys()
    if module_closure((binding.workflow.module,)) - effective:
        raise UserPreferencesError(403, "module_disabled", "A required ERP module is inactive")
    if key not in policy["active_integration_keys"]:
        raise UserPreferencesError(403, "integration_disabled", "This ERP integration is inactive")
    return {**policy, "connector_binding": binding}


def lock_admission(scope):
    lock = ModuleAdmissionLock.__table__
    return GuardedStatement(
        update(lock)
        .where(lock.c.environment_uid == UUID(str(scope)))
        .values(lock_marker=0)
        .returning(lock.c.environment_uid),
        expect_rows=1,
        label=LOCK_LABEL,
    )


def guard_active(scope, module_keys, source_uid, *, local=False, policy_version=None):
    store = configured_store(local=local, policy_only=True)
    source_uid = UUID(str(source_uid))
    if source_uid != store.data_source_uid or (local and require_local_runtime() != source_uid):
        raise UserPreferencesError(
            503,
            "module_policy_source_mismatch",
            "ERP module policy and business writes must share the governed DataSource",
        )
    policy = require_active(scope, module_keys, local=local)
    if policy_version is not None and policy["version"] != policy_version:
        raise UserPreferencesError(409, "module_policy_changed", "ERP module policy changed; retry")
    version = policy["version"]
    model = EnvironmentModuleActivation.__table__
    return [
        lock_admission(scope),
        GuardedStatement(
            select(model.c.environment_uid).where(
                model.c.environment_uid == UUID(str(scope)),
                model.c.version == version,
            ),
            expect_rows=1,
            label=POLICY_LABEL,
        ),
    ]
