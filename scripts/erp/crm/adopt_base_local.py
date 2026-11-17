"""Explicit local-only extraction; the API never migrates or activates on startup."""

import argparse
import json
import socket
from pathlib import Path
from uuid import UUID

from mainsequence.client import User
from metatables import configure_local_client, upgrade_application
from src.erp.base.store import require_local_runtime
from src.erp.crm.base_adoption.extraction import Extraction
from src.erp.crm.base_adoption.store import Store
from src.erp.crm.platform.catalog import CatalogRegistry


def writers_stopped():
    for port in (38641, 38651):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                raise RuntimeError(
                    f"Stop the local application on port {port} before extraction writes"
                )
        except ConnectionRefusedError:
            continue


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("prepare", "inventory", "copy", "reconcile", "activate")
    )
    parser.add_argument("--source-uid", required=True, type=UUID)
    parser.add_argument("--inventory", type=Path)
    args = parser.parse_args()
    configure_local_client()
    source = str(require_local_runtime())
    if source != str(args.source_uid):
        raise RuntimeError("The verified local DataSource does not match the reviewed source")
    if args.command in ("prepare", "copy", "activate"):
        writers_stopped()
    if args.command == "prepare":
        print(
            json.dumps(
                {
                    "base": upgrade_application("src.erp.base.migrations:migration")["revision"],
                    "crm": upgrade_application("src.erp.crm.migrations:migration")["revision"],
                    "data_source_uid": source,
                }
            )
        )
        return
    actor = User.get_authenticated_user_details().uid
    extraction = Extraction(Store(CatalogRegistry()), actor)
    if args.command == "inventory":
        report = {"data_source_uid": source, "inventory": extraction.inventory()}
        if args.inventory:
            args.inventory.write_text(json.dumps(report, indent=2) + "\n")
    elif args.command == "copy":
        report = extraction.copy()
    elif args.command == "reconcile":
        report = extraction.reconcile()
    else:
        if not args.inventory:
            parser.error("activate requires the reviewed --inventory file")
        report = json.loads(args.inventory.read_text())
        if report["data_source_uid"] != source:
            raise RuntimeError("The inventory belongs to another DataSource")
        report = extraction.activate(report["inventory"])
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
