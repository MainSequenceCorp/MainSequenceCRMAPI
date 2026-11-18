"""Authenticated User Preferences and Environment activation routes."""

import logging
from importlib import import_module
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mainsequence.client import User
from mainsequence.server.fastapi import install_request_identity, reads_as_caller
from src.erp.user_preferences.errors import UserPreferencesError
from src.erp.user_preferences.identity import is_local_person
from src.erp.user_preferences.schemas import (
    ActivationInput,
    ActivationProposal,
    PreferenceInput,
)
from src.erp.user_preferences.scope import (
    provisioned_module_keys,
    scope_for_request,
)
from src.erp.user_preferences.service import Service
from src.erp.user_preferences.store import configured_store

PREFIX = "/api/erp/v1"
logger = logging.getLogger(__name__)


def _active_hosted_person(uid):
    uid = str(uid)
    with reads_as_caller():
        profile = User.get_by_uid(uid)
        if str(profile.uid) != uid or profile.is_active is not True:
            return None
        if profile.identity_type == "human":
            return profile
        if profile.identity_type is not None:
            return None
        # Some human directory projections omit the type. Require an exact
        # human-filtered match instead of treating the missing field as human.
        matches = User.filter(uid=uid, identity_type="human")
    if len(matches) != 1:
        return None
    person = matches[0]
    if (
        str(person.uid) == uid
        and person.is_active is True
        and person.identity_type in (None, "human")
    ):
        return profile
    return None


def _person(*, local):
    requester = User.get_requester()
    if requester is not None:
        return requester
    caller = User.get_logged_user()
    if local:
        # The local launcher only supplies the real signed-in CLI identity.
        profile = User.get_authenticated_user_details()
        if str(profile.uid) != str(caller.uid):
            raise UserPreferencesError(403, "forbidden", "The local SDK identity changed")
        if not is_local_person(profile):
            raise UserPreferencesError(403, "person_required", "User Preferences requires a person")
        return profile
    if _active_hosted_person(caller.uid) is None:
        raise UserPreferencesError(403, "person_required", "User Preferences requires a person")
    return caller


def _reader(actor, *, local):
    def can_read(key):
        if key == "crm":
            if local:
                return True
            from src.erp.crm.platform.hosted_runtime import PlatformPolicy

            caps = PlatformPolicy.from_environment().capabilities(actor)
        else:
            identity = import_module(f"api.erp.{key}.identity")
            module_actor, caps = identity.actor_and_capabilities(local=local)
            if module_actor != actor:
                return False
        return f"{key}.read" in caps

    return can_read


def ready_modules(store, *, local):
    """Check approved module schema/provider bindings against the policy source."""
    ready = set()
    for key in provisioned_module_keys():
        try:
            if key == "crm":
                from src.erp.crm.platform.catalog import CatalogRegistry

                registry = CatalogRegistry()
                registry.validate()
                registry.validate_settings()
                source = registry.data_source_uid
            else:
                module = import_module(f"src.erp.{key}.store")
                source = module.Store(local_only=local).data_source_uid
            if str(source) == str(store.data_source_uid):
                ready.add(key)
        except Exception as error:
            logger.info("ERP module %s is unready (%s)", key, type(error).__name__)
    return frozenset(ready)


def _json_error(status, code, message):
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_app(*, local=False, install_identity=True):
    app = FastAPI(title="ERP User Preferences", version="0.1.0")

    def service(request):
        # These are singleton endpoints. In particular, a user cannot supply a
        # person/Environment selector as a query parameter.
        if request.query_params:
            raise UserPreferencesError(
                422, "invalid_query", "These settings accept no query fields"
            )
        person = _person(local=local)
        scope = scope_for_request(request, local=local)
        return Service(
            configured_store(local=local),
            scope,
            UUID(str(person.uid)),
            can_manage=person.is_organization_admin is True,
        )

    @app.exception_handler(UserPreferencesError)
    async def domain_error(_request, error):
        return _json_error(error.status, error.code, error.message)

    @app.exception_handler(Exception)
    async def unexpected(_request, error):
        logger.exception("User Preferences could not evaluate settings", exc_info=error)
        return _json_error(503, "module_policy_unavailable", "ERP module settings are unavailable")

    @app.get("/healthz")
    def health():
        return {"status": "running", "service": "user_preferences"}

    @app.get(PREFIX + "/bootstrap/")
    def bootstrap(request: Request):
        current = service(request)
        return current.bootstrap(
            ready_modules(current.store, local=local), _reader(current.actor, local=local)
        )

    @app.get(PREFIX + "/user-preferences/")
    def preferences(request: Request):
        return service(request).preferences()

    @app.put(PREFIX + "/user-preferences/")
    def save_preferences(request: Request, payload: PreferenceInput):
        return service(request).save_preferences(payload)

    @app.get(PREFIX + "/modules/")
    def modules(request: Request):
        current = service(request)
        current.require_manager()
        return current.administrator_overview(
            current.administrator_policy(),
            ready_modules(current.store, local=local),
            _reader(current.actor, local=local),
        )

    @app.post(PREFIX + "/modules/preflight/")
    def preflight(request: Request, payload: ActivationProposal):
        current = service(request)
        current.require_manager()
        return current.preflight(payload, ready_modules(current.store, local=local))

    @app.put(PREFIX + "/modules/")
    def save_modules(request: Request, payload: ActivationInput):
        current = service(request)
        current.require_manager()
        ready = ready_modules(current.store, local=local)
        return current.administrator_overview(
            current.save_activation(payload, ready), ready, _reader(current.actor, local=local)
        )

    if install_identity:
        install_request_identity(app)
    return app


app = create_app()
