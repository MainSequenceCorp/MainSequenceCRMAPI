"""Versioned personal settings and administrator activation policy."""

from dataclasses import asdict
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import insert, select, update

from mainsequence.client.exceptions import BadRequestError
from metatables import MetaTableTransactionGuardError
from metatables.compiled_sql.v1 import GuardedStatement
from src.erp.modules import MODULES, REQUIRED_MODULES, WORKFLOWS, active_modules, module_closure

from .admission import lock_admission, read_policy
from .connector_registry import read_bindings
from .errors import UserPreferencesError
from .integrations import integration_provisioned, known_binding
from .metatables import (
    EnvironmentModuleActivation,
    IntegrationActivationChange,
    ModuleActivationChange,
    ModuleAdmissionLock,
    UserPreference,
)
from .schemas import ActivationInput, optional_keys


def now():
    return datetime.now(timezone.utc)


def conflict():
    return UserPreferencesError(409, "version_conflict", "Settings changed; refresh and review")


def preview_target(current, target, provisioned):
    stored = frozenset(current)
    selected = frozenset(target) | REQUIRED_MODULES
    closure = module_closure(selected)
    missing = closure - selected
    removed = stored - selected
    blockers = [
        {
            "code": "active_dependent" if key in removed else "missing_prerequisite",
            "module_key": key,
            "related_module_keys": sorted(
                module for module in selected if key in module_closure([module])
            ),
        }
        for key in sorted(missing)
    ]
    blockers += [
        {
            "code": "module_unavailable",
            "module_key": key,
            "related_module_keys": [],
        }
        for key in sorted(closure - provisioned)
    ]
    before = stored | REQUIRED_MODULES
    affected = []
    for workflow in WORKFLOWS:
        participants = module_closure({workflow.owner, *workflow.required_modules})
        if (participants <= before) != (participants <= selected):
            affected.append(
                {
                    **asdict(workflow),
                    "available_after": participants <= selected and participants <= provisioned,
                }
            )
    return {
        "valid": not blockers,
        "active_module_keys": sorted(target),
        "required_module_keys": sorted(missing - REQUIRED_MODULES),
        "blockers": blockers,
        "affected_features": affected,
    }


class Service:
    def __init__(self, store, scope: UUID, actor: UUID, *, can_manage: bool):
        self.store = store
        self.scope = scope
        self.actor = actor
        self.can_manage = can_manage

    def require_manager(self):
        if not self.can_manage:
            raise UserPreferencesError(
                403, "forbidden", "Only an ERP administrator can manage modules"
            )

    def policy(self):
        return read_policy(self.store, self.scope)

    def administrator_policy(self):
        self.require_manager()
        policy = read_policy(self.store, self.scope, allow_uninitialized=True)
        return policy if policy is not None else {"active_module_keys": [], "version": 0}

    def overview(self, policy, provisioned, can_read):
        keys = frozenset(policy["active_module_keys"]) | REQUIRED_MODULES
        return {
            "active_module_keys": sorted(policy["active_module_keys"]),
            "policy_version": policy["version"],
            "modules": [
                {
                    "key": module.key,
                    "title": module.title,
                    "provisioned": module.key in provisioned,
                    "active": module.key in keys,
                    "required": module.key in REQUIRED_MODULES,
                    "can_access": policy["version"] > 0
                    and module_closure([module.key]) <= keys & provisioned
                    and can_read(module.key),
                    "prerequisites": module.prerequisites,
                }
                for module in MODULES.values()
            ],
        }

    def bootstrap(self, provisioned, can_read):
        return {
            **self.overview(self.policy(), provisioned, can_read),
            "organization_environment_uid": self.scope,
            "preferences": self.preferences(),
            "can_manage": self.can_manage,
        }

    def administrator_overview(self, policy, provisioned, can_read):
        self.require_manager()
        return {
            **self.overview(policy, provisioned, can_read),
            "policy_initialized": policy["version"] > 0,
            "workflows": [asdict(workflow) for workflow in WORKFLOWS],
        }

    def integration_policy(self):
        policy = read_policy(
            self.store, self.scope, allow_uninitialized=self.can_manage, include_integrations=True
        )
        return policy if policy is not None else {
            "active_module_keys": [],
            "active_integration_keys": [],
            "connector_registry_revision": 0,
            "version": 0,
        }

    def _integration_replayed(self, key, payload):
        audit = IntegrationActivationChange.__table__
        event = self.store.one(
            select(audit).where(
                audit.c.environment_uid == self.scope, audit.c.request_uid == payload.request_uid
            )
        )
        if event is None:
            return False
        if (
            str(event["actor_uid"]) != str(self.actor)
            or event["integration_key"] != key
            or event["active"] != payload.active
            or event["version"] != payload.expected_version + 1
        ):
            raise UserPreferencesError(
                409, "request_conflict", "Integration activation request UID was reused"
            )
        return True

    def save_integration(self, key, payload, provisioned):
        self.require_manager()
        if self._integration_replayed(key, payload):
            return self.integration_policy()
        policy = self.integration_policy()
        if policy["version"] != payload.expected_version:
            if self._integration_replayed(key, payload):
                return self.integration_policy()
            raise conflict()
        bindings = read_bindings(self.store, self.scope, policy["connector_registry_revision"])
        binding = known_binding(bindings, key)
        modules = frozenset(policy["active_module_keys"]) | REQUIRED_MODULES
        if payload.active and (
            not integration_provisioned(binding, provisioned)
            or not module_closure((binding.workflow.module,)) <= modules
        ):
            raise UserPreferencesError(
                409, "integration_unavailable", "This integration requires its module to be active and available"
            )
        active = set(policy["active_integration_keys"])
        previous_active = key in active
        if payload.active:
            active.add(key)
        else:
            active.discard(key)
        version = policy["version"] + 1
        stamp = now()
        model = EnvironmentModuleActivation.__table__
        try:
            self._write_versioned(
                [
                    lock_admission(self.scope),
                    GuardedStatement(
                        update(model)
                        .where(
                            model.c.environment_uid == self.scope,
                            model.c.version == policy["version"],
                        )
                        .values(
                            active_integration_keys=sorted(active),
                            actor_uid=self.actor,
                            version=version,
                            updated_at=stamp,
                        )
                        .returning(model.c.environment_uid),
                        expect_rows=1,
                        label="erp_integration_activation_version",
                    ),
                    insert(IntegrationActivationChange.__table__).values(
                        uid=uuid4(),
                        environment_uid=self.scope,
                        request_uid=payload.request_uid,
                        actor_uid=self.actor,
                        occurred_at=stamp,
                        version=version,
                        integration_key=key,
                        previous_active=previous_active,
                        active=payload.active,
                    ),
                ]
            )
        except UserPreferencesError:
            if self._integration_replayed(key, payload):
                return self.integration_policy()
            raise
        return {**policy, "version": version, "active_integration_keys": sorted(active)}

    def _preference_row(self):
        model = UserPreference.__table__
        return self.store.one(
            select(model).where(
                model.c.environment_uid == self.scope, model.c.person_uid == self.actor
            )
        )

    def preferences(self):
        row = self._preference_row()
        if row is None:
            return {"hidden_module_keys": [], "version": 0}
        return {"hidden_module_keys": row["hidden_module_keys"], "version": row["version"]}

    def save_preferences(self, payload):
        row = self._preference_row()
        version = payload.expected_version
        if version != (row["version"] if row else 0):
            raise conflict()
        data = {
            "hidden_module_keys": payload.hidden_module_keys,
            "version": version + 1,
            "updated_at": now(),
        }
        model = UserPreference.__table__
        if version == 0:
            # The admission row serializes two first saves for the same scope,
            # even when neither request sees a preference row initially.
            absent = select(model.c.uid).where(
                model.c.environment_uid == self.scope, model.c.person_uid == self.actor
            )
            steps = [
                lock_admission(self.scope),
                GuardedStatement(absent, expect_rows=0, label="erp_preference_absent"),
                insert(model).values(
                    uid=uuid4(), environment_uid=self.scope, person_uid=self.actor, **data
                ),
            ]
        else:
            steps = [
                GuardedStatement(
                    update(model)
                    .where(
                        model.c.environment_uid == self.scope,
                        model.c.person_uid == self.actor,
                        model.c.version == version,
                    )
                    .values(**data)
                    .returning(model.c.uid),
                    expect_rows=1,
                    label="erp_preference_version",
                )
            ]
        self._write_versioned(steps)
        return {"hidden_module_keys": data["hidden_module_keys"], "version": data["version"]}

    def preflight(self, payload, provisioned):
        policy = self.administrator_policy()
        if policy["version"] != payload.expected_version:
            raise conflict()
        return preview_target(policy["active_module_keys"], payload.active_module_keys, provisioned)

    def _replayed(self, payload):
        audit = ModuleActivationChange.__table__
        event = self.store.one(
            select(audit).where(
                audit.c.environment_uid == self.scope, audit.c.request_uid == payload.request_uid
            )
        )
        if event is None:
            return False
        if (
            str(event["actor_uid"]) != str(self.actor)
            or event["active_module_keys"] != payload.active_module_keys
            or event["version"] != payload.expected_version + 1
        ):
            raise UserPreferencesError(409, "request_conflict", "Activation request UID was reused")
        return True

    def _write_versioned(self, statements):
        try:
            self.store.write(statements)
        except MetaTableTransactionGuardError as exc:
            raise conflict() from exc

    def save_activation(self, payload, provisioned):
        self.require_manager()
        if self._replayed(payload):
            return self.policy()
        policy = self.administrator_policy()
        if policy["version"] != payload.expected_version:
            if self._replayed(payload):
                return self.policy()
            raise conflict()
        before = policy["active_module_keys"]
        after = payload.active_module_keys
        preview = preview_target(before, after, provisioned)
        if not preview["valid"]:
            raise UserPreferencesError(
                409, "invalid_module_set", "Review missing prerequisites and unavailable modules"
            )
        if policy["version"] == 0:
            return self._initialize(payload)
        stamp = now()
        version = policy["version"] + 1
        model = EnvironmentModuleActivation.__table__
        try:
            self._write_versioned(
                [
                    lock_admission(self.scope),
                    GuardedStatement(
                        update(model)
                        .where(
                            model.c.environment_uid == self.scope,
                            model.c.version == policy["version"],
                        )
                        .values(
                            active_module_keys=after,
                            actor_uid=self.actor,
                            version=version,
                            updated_at=stamp,
                        )
                        .returning(model.c.environment_uid),
                        expect_rows=1,
                        label="erp_module_activation_version",
                    ),
                    insert(ModuleActivationChange.__table__).values(
                        uid=uuid4(),
                        environment_uid=self.scope,
                        request_uid=payload.request_uid,
                        previous_module_keys=before,
                        active_module_keys=after,
                        actor_uid=self.actor,
                        version=version,
                        occurred_at=stamp,
                    ),
                ]
            )
        except UserPreferencesError:
            if self._replayed(payload):
                return self.policy()
            raise
        return {"active_module_keys": after, "version": version}

    def _initialize(self, payload):
        model = EnvironmentModuleActivation.__table__
        target = payload.active_module_keys
        stamp = now()
        try:
            self.store.write(
                [
                    insert(ModuleAdmissionLock.__table__).values(
                        environment_uid=self.scope, lock_marker=0
                    ),
                    insert(model).values(
                        environment_uid=self.scope,
                        active_module_keys=target,
                        actor_uid=self.actor,
                        version=1,
                        updated_at=stamp,
                    ),
                    insert(ModuleActivationChange.__table__).values(
                        uid=uuid4(),
                        environment_uid=self.scope,
                        request_uid=payload.request_uid,
                        actor_uid=self.actor,
                        previous_module_keys=[],
                        active_module_keys=target,
                        version=1,
                        occurred_at=stamp,
                    ),
                ]
            )
        except BadRequestError as exc:
            if self._replayed(payload):
                return self.policy()
            if self.administrator_policy()["version"] > 0:
                raise conflict() from exc
            raise
        return self.policy()

    def seed(self, keys, provisioned):
        policy = self.administrator_policy()
        target = optional_keys(list(keys))
        active_modules(target)
        if not (frozenset(target) | REQUIRED_MODULES) <= provisioned:
            raise UserPreferencesError(
                409, "module_unavailable", "Initial modules must be provisioned"
            )
        if policy["version"] > 0:
            return policy
        return self._initialize(
            ActivationInput(active_module_keys=target, expected_version=0, request_uid=uuid4())
        )
