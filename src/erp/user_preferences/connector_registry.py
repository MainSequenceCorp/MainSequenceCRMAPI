"""Validate and atomically publish the Environment-scoped connector catalog."""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
import yaml
from pydantic import ValidationError
from sqlalchemy import insert, select, update

from mainsequence.client import CodeRepositoryBranch, ResourceRelease
from metatables import MetaTableTransactionGuardError
from metatables.compiled_sql.v1 import GuardedStatement

from .errors import UserPreferencesError
from .integrations import (
    GOOGLE_KEY,
    INSTALLATION_SETTING,
    LOCAL_TOKEN_HEADER,
    LOCAL_TOKEN_SETTING,
    RELEASE_SETTING,
    WORKFLOWS,
    Binding,
)
from .metatables import ConnectorRegistryRevision, EnvironmentModuleActivation
from .schemas import ConnectorRegistryDocument, WorkflowSettings

KEY = re.compile(r"[a-z][a-z0-9-]{0,47}")
MANIFEST_PATH = "/api/connector/v1/manifest/"
LOCAL_TARGETS_SETTING = "ERP_CONNECTOR_LOCAL_TARGETS"


class RegistryLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        # Registry documents are small and self-contained. Reject aliases before
        # composition so validation cannot walk an expanded or cyclic document.
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("YAML aliases are not accepted")
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        mapping = super().construct_mapping(node, deep=deep)
        if len(mapping) != len(node.value):
            raise yaml.YAMLError("Duplicate YAML key")
        return mapping


def invalid(message, code="invalid_connector_registry", status=422):
    return UserPreferencesError(status, code, message)


def parse_registry(source, scope):
    try:
        document = ConnectorRegistryDocument.model_validate(yaml.load(source, Loader=RegistryLoader))
    except (ValidationError, yaml.YAMLError, RecursionError) as exc:
        raise invalid(
            "Invalid registry YAML. Supply a release UID and unique workflow keys. "
            "V2 settings may specify admin_only and placement for listed workflows."
        ) from exc
    if document.environment_uid != scope:
        raise invalid("Registry YAML belongs to a different Environment", "environment_mismatch")
    for key, entry in document.connectors.items():
        if not KEY.fullmatch(key):
            raise invalid("Connector keys must be lowercase slugs")
        for workflow in entry.workflows:
            if workflow not in WORKFLOWS:
                raise invalid("An ERP workflow in the registry is unsupported", "unknown_workflow")
    return document


@dataclass(frozen=True)
class LocalTarget:
    origin: str
    token: str | None = field(repr=False)


def local_target(release_uid):
    release = str(release_uid)
    try:
        targets = json.loads(os.environ.get(LOCAL_TARGETS_SETTING, "{}"))
        configured = targets.get(release)
        if configured is None and release == os.environ.get(RELEASE_SETTING):
            configured = {
                "origin": os.environ.get("ERP_GOOGLE_CONTACTS_CONNECTOR_LOCAL_ORIGIN"),
                "token": os.environ.get(LOCAL_TOKEN_SETTING),
            }
        origin = urlsplit(configured["origin"])
        token = configured.get("token")
        if (
            origin.scheme != "http" or origin.hostname not in {"127.0.0.1", "localhost", "::1"}
            or not origin.port or origin.path not in {"", "/"} or origin.query or origin.fragment
            or origin.username or origin.password or (token is not None and len(token) < 32)
        ):
            raise ValueError
        return LocalTarget(origin.geturl().rstrip("/"), token)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise invalid("The connector has no approved loopback target", "connector_unavailable", 503) from exc


def verified_release(release_uid, scope, *, local):
    try:
        if local:
            target = local_target(release_uid)
            with httpx.Client(timeout=5, trust_env=False) as client:
                response = client.get(
                    target.origin + MANIFEST_PATH,
                    headers={LOCAL_TOKEN_HEADER: target.token} if target.token else None,
                )
            workload = None
        else:
            release = ResourceRelease.get(pk=str(release_uid))
            branch = CodeRepositoryBranch.get(pk=release.code_repository_branch_uid)
            if (
                str(release.uid) != str(release_uid) or release.release_kind != "fastapi"
                or str(branch.uid) != str(release.code_repository_branch_uid)
                or str(branch.organization_environment_uid) != str(scope)
            ):
                raise invalid("Connector release must be a FastAPI release in this Environment")
            workload = UUID(release.workload_user_uid)
            response = release.request(
                "GET", MANIFEST_PATH, timeout=5, ready_timeout=10, allow_redirects=False
            )
        if response.status_code != 200:
            raise ValueError
        manifest = response.json()
        if not isinstance(manifest, dict) or not isinstance(manifest.get("capabilities"), dict):
            raise ValueError
        return workload, manifest
    except UserPreferencesError:
        raise
    except Exception as exc:
        raise invalid("The approved connector manifest could not be read", "connector_unavailable", 503) from exc


def read_bindings(store, scope, revision):
    if revision == 0:
        return {}
    table = ConnectorRegistryRevision.__table__
    row = store.one(select(table.c.bindings).where(table.c.environment_uid == scope, table.c.revision == revision))
    if row is None:
        raise invalid("The published ERP connector revision is unavailable", "connector_registry_unavailable", 503)
    try:
        bindings = [Binding.model_validate(binding) for binding in row["bindings"]]
        if any(binding.workflow_key not in WORKFLOWS for binding in bindings):
            raise ValueError
        return {binding.key: binding for binding in bindings}
    except (TypeError, ValueError) as exc:
        raise invalid("The published ERP connector revision is invalid", "connector_registry_unavailable", 503) from exc


def cleanup_registrations(store, scope, connector_key, installation_uid, *, workload_uid=None):
    """Find historically approved targets for a close-only lifecycle request."""
    table = ConnectorRegistryRevision.__table__
    before = None
    seen = set()
    while True:
        query = select(table.c.revision, table.c.bindings).where(table.c.environment_uid == scope)
        if before is not None:
            query = query.where(table.c.revision < before)
        rows = store.rows(query.order_by(table.c.revision.desc()), limit=25)
        if not rows:
            return
        for row in rows:
            for entry in row["bindings"]:
                if (
                    entry["connector_key"] != connector_key
                    or entry["installation_uid"] != str(installation_uid)
                    or (workload_uid is not None and entry["workload_uid"] != str(workload_uid))
                ):
                    continue
                release = entry["release_uid"]
                if release not in seen:
                    seen.add(release)
                    yield Binding.model_validate(entry)
        before = rows[-1]["revision"]


def _installation(key, release_uid, previous, revision):
    if previous:
        return previous[0].installation_uid
    # Adopt an existing Google installation only on the first publication
    # and only when the published target matches the former approved target.
    if revision == 1 and key == GOOGLE_KEY and str(release_uid) == os.environ.get(RELEASE_SETTING):
        try:
            return UUID(os.environ[INSTALLATION_SETTING])
        except KeyError:
            pass
        except ValueError as exc:
            raise invalid("Existing Google installation identity is invalid") from exc
    return uuid4()


def _resolve(document, scope, previous, revision, *, local):
    resolved = {}
    for key, entry in document.connectors.items():
        workload, manifest = verified_release(entry.release_uid, scope, local=local)
        if manifest.get("connector_key") != key:
            raise invalid("The connector manifest identity does not match its registry key")
        installations = [binding for binding in previous.values() if binding.connector_key == key]
        uid = _installation(key, entry.release_uid, installations, revision)
        for workflow_key in entry.workflows:
            workflow = WORKFLOWS[workflow_key]
            available = manifest["capabilities"]
            if (
                manifest.get("contract_version") != workflow.contract
                or not all(capability in available for capability in workflow.manifest_capabilities)
            ):
                raise invalid("The connector manifest does not support a selected workflow", "incompatible_connector")
            name = workflow.binding_key(key)
            settings = entry.workflow_settings.get(workflow_key, WorkflowSettings())
            binding = Binding(
                key=name, connector_key=key, workflow_key=workflow_key,
                installation_uid=uid, release_uid=entry.release_uid, workload_uid=workload,
                generation=revision, **settings.model_dump(),
            )
            old = previous.get(name)
            if old and binding.model_copy(update={
                "generation": old.generation, "admin_only": old.admin_only,
                "placement": old.placement,
            }) == old:
                binding = binding.model_copy(update={"generation": old.generation})
            resolved[name] = binding
    return resolved


def publish(service, payload, *, local):
    from .admission import lock_admission

    service.require_manager()
    document = parse_registry(payload.yaml, service.scope)
    policy = service.integration_policy()
    current = policy["connector_registry_revision"]
    if current != payload.expected_revision:
        raise invalid("Connector registry changed. Reload and try again.", "registry_revision_changed", 409)
    if not policy["version"]:
        raise invalid("Initialize the ERP module policy before publishing connectors", "module_policy_unavailable", 409)
    previous = read_bindings(service.store, service.scope, current)
    revision = current + 1
    resolved = _resolve(document, service.scope, previous, revision, local=local)
    active_keys = [
        key for key in policy["active_integration_keys"]
        if key in resolved and (
            (key in previous and resolved[key].generation == previous[key].generation)
            or (
                current == 0 and resolved[key].connector_key == GOOGLE_KEY
                and str(resolved[key].installation_uid) == os.environ.get(INSTALLATION_SETTING)
            )
        )
    ]
    now = datetime.now(timezone.utc)
    state = EnvironmentModuleActivation.__table__
    try:
        service.store.write([
            lock_admission(service.scope),
            GuardedStatement(
                update(state).where(
                    state.c.environment_uid == service.scope,
                    state.c.connector_registry_revision == current,
                    state.c.version == policy["version"],
                ).values(
                    connector_registry_revision=revision, version=policy["version"] + 1,
                    active_integration_keys=active_keys, updated_at=now, actor_uid=service.actor,
                ).returning(state.c.environment_uid),
                expect_rows=1,
                label="erp_connector_registry_version",
            ),
            insert(ConnectorRegistryRevision.__table__).values(
                environment_uid=service.scope, revision=revision, published_by_uid=service.actor,
                published_at=now, document_yaml=payload.yaml,
                bindings=[binding.model_dump(mode="json") for binding in resolved.values()],
            ),
        ])
    except MetaTableTransactionGuardError as exc:
        raise invalid("Connector registry or module policy changed. Reload and try again.", "registry_revision_changed", 409) from exc
    return revision
