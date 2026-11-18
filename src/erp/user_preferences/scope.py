"""Resolve Environment and governed storage from verified process/request context."""

import os
from uuid import UUID

from metatables import get_runtime_status

from .errors import UserPreferencesError

SOURCE_SETTING = "ERP_USER_PREFERENCES_DATA_SOURCE_UID"
LOCAL_SCOPE_SETTING = "ERP_USER_PREFERENCES_LOCAL_SCOPE_UID"
HOSTED_SCOPE_SETTING = "MAINSEQUENCE_ORGANIZATION_ENVIRONMENT_UID"
MODULES_SETTING = "ERP_USER_PREFERENCES_PROVISIONED_MODULES"


def configured_uuid(value, *, code="module_policy_unavailable"):
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise UserPreferencesError(503, code, "ERP module settings scope is unavailable") from exc


def require_local_runtime() -> UUID:
    state = get_runtime_status()
    source = state.get("data_source") or {}
    bootstrap = state.get("bootstrap") or {}
    if not (
        state.get("local_mode") is True
        and state.get("dialect") == "sqlite"
        and source.get("class_type") == "sqlite"
        and bootstrap.get("active") is True
        and bootstrap.get("status") == "ready"
        and not state.get("data_source_error")
    ):
        raise UserPreferencesError(
            503, "module_policy_unavailable", "User Preferences requires ready local SQLite"
        )
    return configured_uuid(source.get("uid"))


def configured_source(*, local=False) -> UUID:
    expected = configured_uuid(os.environ.get(SOURCE_SETTING))
    if local and require_local_runtime() != expected:
        raise UserPreferencesError(
            503, "module_policy_unavailable", "User Preferences local DataSource changed"
        )
    return expected


def configured_scope(*, local=False) -> UUID:
    if local:
        if os.environ.get(HOSTED_SCOPE_SETTING):
            raise UserPreferencesError(
                503, "module_policy_unavailable", "Local and hosted ERP scope cannot be combined"
            )
        source = configured_uuid(os.environ.get(SOURCE_SETTING))
        return configured_uuid(os.environ.get(LOCAL_SCOPE_SETTING, str(source)))
    return configured_uuid(os.environ.get(HOSTED_SCOPE_SETTING))


def scope_for_request(request, *, local=False) -> UUID:
    scope = configured_scope(local=local)
    if (
        not local
        and configured_uuid(getattr(request.state, "organization_environment_uid", None)) != scope
    ):
        raise UserPreferencesError(
            403, "environment_mismatch", "Access is outside the active ERP Environment"
        )
    return scope


def provisioned_module_keys() -> frozenset[str]:
    from src.erp.modules import MODULES, REQUIRED_MODULES

    values = frozenset(
        v.strip() for v in os.environ.get(MODULES_SETTING, "").split(",") if v.strip()
    )
    if values - MODULES.keys() or not REQUIRED_MODULES <= values:
        raise UserPreferencesError(
            503, "module_policy_unavailable", "ERP release availability is not configured"
        )
    return values
