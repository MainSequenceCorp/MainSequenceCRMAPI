"""Authenticated User Preferences and Environment activation routes."""

import asyncio
import logging
from hmac import compare_digest
from importlib import import_module
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter
from starlette.concurrency import run_in_threadpool

from mainsequence.client import OrganizationEnvironment, User
from mainsequence.server.fastapi import install_request_identity
from src.agents.assistant_contracts import AssistantMetadata
from src.agents.crm.discovery import resolve_assistant
from src.erp.catalog_bindings import load_active_catalog
from src.erp.user_preferences.admission import require_integration
from src.erp.user_preferences.connector_registry import local_target, publish, read_bindings
from src.erp.user_preferences.errors import UserPreferencesError
from src.erp.user_preferences.identity import (
    active_hosted_person,
    request_person as _person,
    require_workflow_admin,
)
from src.erp.user_preferences.integrations import LOCAL_TOKEN_HEADER, integration_overview
from src.erp.user_preferences.schemas import (
    ActivationInput,
    ActivationProposal,
    ConnectorRegistryPublication,
    IntegrationActivationInput,
    IntegrationAdmissionInput,
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
assistant_metadata = TypeAdapter(AssistantMetadata)


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


def _workflow_access(actor, workflow, *, local):
    if workflow.module == "finance":
        from api.erp.finance.identity import actor_and_capabilities

        person, capabilities = actor_and_capabilities(local=local)
        return actor == person and workflow.permissions <= capabilities
    if local:
        # All CRM business permissions except export apply to the locally verified person.
        return True
    from src.erp.crm.platform.hosted_runtime import PlatformPolicy

    return workflow.permissions <= PlatformPolicy.from_environment().capabilities(actor)


def _connector_actor(request, actor, scope, binding, *, local, operation):
    """Admit the actor named by the exact configured provider workload."""
    if local:
        expected = local_target(binding.release_uid).token
        supplied = request.headers.get(LOCAL_TOKEN_HEADER, "")
        if not expected or not compare_digest(expected.encode(), supplied.encode()):
            raise UserPreferencesError(403, "forbidden", "Connector authorization is required")
        person = _person(local=True)
        if str(person.uid) != str(actor):
            raise UserPreferencesError(403, "forbidden", "Connector actor is not the local person")
        require_workflow_admin(binding, lambda: person)
        return

    caller = User.get_logged_user()
    if binding.workload_uid != UUID(str(caller.uid)):
        raise UserPreferencesError(403, "forbidden", "Connector authorization is required")
    from src.erp.crm.platform.hosted_runtime import PlatformPolicy

    # Directory facts are read under the settings caller's authority. The
    # connector authenticated the human and checked the requested operation.
    person = active_hosted_person(actor)
    if person is None:
        raise UserPreferencesError(403, "forbidden", "CRM import permission is required")
    organization = OrganizationEnvironment.get_by_uid(str(scope)).organization_owner_uid
    actor_org = getattr(person.organization, "uid", None)
    teams = {str(getattr(team, "uid", team)) for team in person.organization_teams}
    if binding.workflow.module == "finance":
        from api.erp.finance.identity import finance_capabilities, finance_role_groups

        required = "finance.configure" if operation == "configure" else "finance.read"
        if str(actor_org) != str(organization) or required not in finance_capabilities(
            teams, person.is_organization_admin is True, finance_role_groups()
        ):
            raise UserPreferencesError(403, "forbidden", "Finance permission is required")
        require_workflow_admin(binding, lambda: person)
        return
    if (
        actor_org != organization
        or (
            person.is_organization_admin is not True
            and not teams & PlatformPolicy.from_environment().writer_team_uids
        )
    ):
        raise UserPreferencesError(403, "forbidden", "CRM import permission is required")
    require_workflow_admin(binding, lambda: person)


def ready_modules(store, *, local, candidates=None):
    """Check approved module schema/provider bindings against the policy source."""
    provisioned = provisioned_module_keys()
    keys = provisioned if candidates is None else provisioned & candidates
    expected = {}
    for key in sorted(keys):
        models = import_module(f"src.erp.{key}.metatables").MODELS
        expected[key] = models.values() if isinstance(models, dict) else models
    catalog = load_active_catalog(
        model.__metatable_identifier__ for models in expected.values() for model in models
    )
    policy_source = str(store.data_source_uid)
    ready = set()
    for key in expected:
        try:
            if key == "crm":
                from src.erp.crm.platform.catalog import CatalogRegistry

                registry = CatalogRegistry(catalog=catalog)
                registry.validate()
                registry.validate_settings()
                source = registry.data_source_uid
            else:
                module = import_module(f"src.erp.{key}.store")
                source = module.Store(local_only=local, catalog=catalog).data_source_uid
            if str(source) == policy_source:
                ready.add(key)
        except Exception as error:
            logger.info("ERP module %s is unready (%s)", key, type(error).__name__)
    return frozenset(ready)


def service_for(request, *, local, person=None):
    person = _person(local=local) if person is None else person
    return Service(
        configured_store(local=local),
        scope_for_request(request, local=local),
        UUID(str(person.uid)),
        can_manage=person.is_organization_admin is True,
    )


def module_overview(current, *, local, policy=None):
    can_read = _reader(current.actor, local=local)

    def readable(key):
        try:
            return can_read(key)
        except Exception as error:
            logger.info("ERP module %s permission is unavailable (%s)", key, type(error).__name__)
            return False

    return current.overview(
        current.policy() if policy is None else policy,
        ready_modules(current.store, local=local),
        readable,
    )


def _bootstrap_for(request, *, local):
    person = _person(local=local)
    current = service_for(request, local=local, person=person)
    name = " ".join(filter(None, (
        getattr(person, "first_name", None), getattr(person, "last_name", None),
    ))) or getattr(person, "username", None)
    return {
        **module_overview(current, local=local),
        "organization_environment_uid": current.scope,
        "preferences": current.preferences(),
        "can_manage": current.can_manage,
        "current_user": {"uid": current.actor, "display_name": name},
    }


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
        return service_for(request, local=local)

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
    async def bootstrap(request: Request):
        if request.query_params:
            raise UserPreferencesError(
                422, "invalid_query", "These settings accept no query fields"
            )
        document = await run_in_threadpool(_bootstrap_for, request, local=local)
        try:
            assistant = await asyncio.wait_for(
                resolve_assistant(
                    getattr(app.state, "crm_local_tau_origin", None), allow_platform=not local
                ),
                timeout=2.0,
            )
        except (TimeoutError, RuntimeError):
            assistant = {"enabled": False, "runtime": None, "agent_uid": None, "environment_uid": None}
        assistant["display_name"] = "ERP assistant"
        document["assistant"] = assistant_metadata.validate_python(assistant).model_dump(mode="json")
        return document

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

    def overview(current, policy):
        return integration_overview(
            policy,
            read_bindings(current.store, current.scope, policy["connector_registry_revision"]),
            provisioned_module_keys(),
            may_use=lambda workflow: _workflow_access(current.actor, workflow, local=local),
            can_manage=current.can_manage,
        )

    @app.get(PREFIX + "/integrations/")
    def integrations(request: Request):
        current = service(request)
        return overview(current, current.integration_policy())

    @app.get(PREFIX + "/connector-registry/")
    def registry(request: Request):
        current = service(request)
        current.require_manager()
        policy = current.integration_policy()
        revision = policy["connector_registry_revision"]
        bindings = read_bindings(current.store, current.scope, revision)
        return {"revision": revision, "bindings": list(bindings.values())}

    @app.post(PREFIX + "/connector-registry/revisions/", status_code=201)
    def publish_registry(request: Request, payload: ConnectorRegistryPublication):
        current = service(request)
        revision = publish(current, payload, local=local)
        return {"revision": revision}

    @app.put(PREFIX + "/integrations/{key}/")
    def save_integration(request: Request, key: str, payload: IntegrationActivationInput):
        current = service(request)
        policy = current.save_integration(key, payload, provisioned_module_keys())
        return overview(current, policy)

    @app.post(PREFIX + "/integrations/{key}/admission/")
    def connector_admission(request: Request, key: str, payload: IntegrationAdmissionInput):
        if request.query_params:
            raise UserPreferencesError(422, "invalid_query", "Admission accepts no query fields")
        scope = scope_for_request(request, local=local)
        policy = require_integration(scope, key, local=local)
        binding = policy["connector_binding"]
        _connector_actor(request, payload.actor_uid, scope, binding, local=local, operation=payload.operation)
        return {
            "policy_version": policy["version"],
            "binding": key,
            "binding_generation": binding.generation,
            "environment_uid": scope,
            "installation_uid": binding.installation_uid,
        }

    if install_identity:
        install_request_identity(app)
    return app


app = create_app()
