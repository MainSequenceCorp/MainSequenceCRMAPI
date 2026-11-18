"""Reconcile the provisioned ERP schemas before deploying the API and assistant."""

import logging
from collections.abc import Iterable
from uuid import UUID

from metatables import configure_local_client, get_runtime_status, upgrade_application
from src.erp.modules import resolve_modules
from src.erp.user_preferences.scope import configured_source, provisioned_module_keys

USER_PREFERENCES_PROVIDER = "src.erp.user_preferences.migrations:migration"


def migration_providers(module_keys: Iterable[str]) -> tuple[str, ...]:
    """Order the configured modules while keeping independent migration histories."""
    providers = tuple(module.migration_provider for module in resolve_modules(module_keys))
    return (*providers, USER_PREFERENCES_PROVIDER)


def _verified_source(*, local: bool) -> UUID:
    expected = configured_source(local=local)
    if local:
        return expected
    status = get_runtime_status()
    bootstrap = status.get("bootstrap") or {}
    source = status.get("data_source") or {}
    if not (
        status.get("local_mode") is False
        and bootstrap.get("active") is True
        and bootstrap.get("status") == "ready"
        and not status.get("data_source_error")
        and source.get("uid") == str(expected)
    ):
        raise RuntimeError("ERP migrations require the ready, configured hosted DataSource")
    return expected


def main(*, local: bool = False) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("metatables.migrations.runner").setLevel(logging.INFO)
    providers = migration_providers(provisioned_module_keys())
    if local:
        configure_local_client()
    for provider in providers:
        source = _verified_source(local=local)
        result = upgrade_application(provider)
        if str(result["data_source_uid"]) != str(source):
            raise RuntimeError(f"{provider} returned an unexpected ERP DataSource")
        state = "migrated" if result["migrated"] else "already current"
        print(
            f"{provider}: {result['revision']} ({state}; catalog reconciled) "
            f"on {result['data_source_uid']}",
            flush=True,
        )


if __name__ == "__main__":
    main()
