"""Per-request policy and per-tool ERP admission using the verified SDK identity."""

from contextvars import ContextVar
from dataclasses import dataclass, field
from importlib import import_module
from uuid import UUID

from fastapi import Request

from api.erp.crm.mcp_server import _require_hosted_person
from api.erp.crm.service_adapter import bind_local_crm_request, context_for
from api.erp.user_preferences import main as preferences
from mainsequence.client import User
from src.erp.crm.platform.runtime import CAPABILITIES
from src.erp.module_access import admission_for
from src.erp.modules import module_closure
from src.erp.user_preferences.errors import UserPreferencesError
from src.erp.user_preferences.scope import provisioned_module_keys
from src.erp.user_preferences.service import Service


@dataclass
class Scope:
    request: Request
    apps: dict
    local: bool
    identity_mode: str
    person: object
    settings: Service
    policy: dict
    provisioned: frozenset[str]
    _capabilities: dict[str, frozenset[str]] = field(default_factory=dict)
    _permission_errors: dict[str, UserPreferencesError] = field(default_factory=dict)
    _ready: dict[str, bool] = field(default_factory=dict)

    @classmethod
    def prepare(cls, request, apps):
        local = request.app.state.mainsequence_request_identity["mode"] == "local"
        if local:
            identity_mode = "local"
            person = preferences._person(local=True)
        else:
            identity_mode = _require_hosted_person(request)
            person = User.get_requester() or User.get_logged_user()
        try:
            settings = preferences.service_for(request, local=local, person=person)
            policy = settings.policy()
        except UserPreferencesError:
            raise
        except Exception as error:
            raise UserPreferencesError(503, "unavailable", "ERP policy is unavailable") from error
        return cls(
            request,
            apps,
            local,
            identity_mode,
            person,
            settings,
            policy,
            provisioned_module_keys(),
        )

    def capabilities(self, owner):
        if owner not in self._capabilities:
            if owner == "crm":
                if self.local:
                    bind_local_crm_request(self.request, self.person)
                context = context_for(self.request)
                actor = context.actor_uid
                capabilities = frozenset(context.policy.capabilities(actor))
                if not capabilities <= CAPABILITIES:
                    raise UserPreferencesError(
                        503, "unavailable", "CRM permissions are unavailable"
                    )
            else:
                identity = import_module(f"api.erp.{owner}.identity")
                actor, capabilities = identity.actor_and_capabilities(local=self.local)
            if UUID(str(actor)) != self.settings.actor:
                raise UserPreferencesError(403, "forbidden", "ERP requester changed")
            self._capabilities[owner] = frozenset(capabilities)
        return self._capabilities[owner]

    def admit(self, entry):
        if entry.organization_admin and not self.settings.can_manage:
            raise UserPreferencesError(403, "forbidden", "ERP administration is required")
        if entry.local_only and not self.local:
            raise UserPreferencesError(
                503, "unavailable", "This operation requires the local runtime"
            )
        admitted = admission_for(
            self.settings.scope,
            local=self.local,
            policy=self.policy,
            provisioned=self.provisioned,
        )
        modules = entry.required_modules
        if entry.owner_module != "user_preferences":
            modules = modules | {entry.owner_module}
        for key in modules:
            admitted.require(key)
        if entry.owner_capabilities:
            owner = entry.owner_module
            if owner in self._permission_errors:
                raise self._permission_errors[owner]
            try:
                capabilities = self.capabilities(owner)
            except UserPreferencesError as error:
                self._permission_errors[owner] = error
                raise
            except Exception as error:
                unavailable = UserPreferencesError(
                    503, "unavailable", "ERP permissions are unavailable"
                )
                self._permission_errors[owner] = unavailable
                raise unavailable from error
            if not any(required <= capabilities for required in entry.owner_capabilities):
                raise UserPreferencesError(403, "forbidden", "ERP action is not permitted")
        keys = module_closure(modules)
        unchecked = keys - self._ready.keys()
        if unchecked:
            ready = preferences.ready_modules(
                self.settings.store, local=self.local, candidates=unchecked
            )
            self._ready.update({key: key in ready for key in unchecked})
        if any(not self._ready[key] for key in keys):
            raise UserPreferencesError(503, "unavailable", "A required ERP module is unavailable")
        if entry.available is not None and not entry.available(self):
            raise UserPreferencesError(503, "unavailable", "This ERP workflow is unavailable")
        return admitted


active_scope: ContextVar[Scope] = ContextVar("erp_mcp_scope")
