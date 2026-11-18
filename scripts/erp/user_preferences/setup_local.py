"""Apply the User Preferences provider and seed a reviewed local activation set."""

import argparse
import os
from uuid import UUID

from mainsequence.client import User
from metatables import configure_local_client, upgrade_application
from src.erp.user_preferences.identity import is_local_person
from src.erp.user_preferences.scope import (
    MODULES_SETTING,
    SOURCE_SETTING,
    configured_scope,
    configured_source,
    provisioned_module_keys,
)
from src.erp.user_preferences.service import Service
from src.erp.user_preferences.store import configured_store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-uid", type=UUID, required=True)
    parser.add_argument(
        "--provisioned", required=True, help="Comma-separated provisioned module keys"
    )
    parser.add_argument(
        "--active", required=True, help="Comma-separated optional active module keys"
    )
    args = parser.parse_args()

    os.environ[SOURCE_SETTING] = str(args.source_uid)
    os.environ[MODULES_SETTING] = args.provisioned
    configure_local_client()
    scope = configured_scope(local=True)
    configured_source(local=True)
    provisioned = provisioned_module_keys()
    actor = User.get_authenticated_user_details()
    if not is_local_person(actor) or actor.is_organization_admin is not True:
        raise RuntimeError(
            "Local preferences setup requires a signed-in Organization administrator"
        )
    result = upgrade_application("src.erp.user_preferences.migrations:migration")
    service = Service(configured_store(local=True), scope, UUID(str(actor.uid)), can_manage=True)
    policy = service.seed(
        [key.strip() for key in args.active.split(",") if key.strip()], provisioned
    )
    print(
        {
            "revision": result["revision"],
            "data_source_uid": str(args.source_uid),
            "scope_uid": str(scope),
            "active_module_keys": policy["active_module_keys"],
            "policy_version": policy["version"],
        }
    )


if __name__ == "__main__":
    main()
