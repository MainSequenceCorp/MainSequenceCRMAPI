"""Owned actual stock setup for browser workflows, with cleanup after every run."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from sqlalchemy import delete

from src.erp.catalog.metatables import AuditEvent, Item
from src.erp.catalog.schemas import ItemInput
from tests.erp.inventory.conftest import inventory_services, stock


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", type=Path, required=True)
    args = parser.parse_args()
    fixture = stock.__wrapped__(inventory_services.__wrapped__())
    f = next(fixture)
    extra = None
    with TemporaryDirectory(prefix="inventory-browser-") as directory:
        path = Path(directory) / "fixture.json"
        owned = Path(directory) / "owned.json"
        owned.write_text("[]")
        try:
            extra = f["catalog"].save(
                "items",
                {
                    **{k: f["item"][k] for k in ItemInput.model_fields},
                    "name": "Browser stock product " + uuid4().hex[:8],
                    "code": "BROWSER-" + uuid4().hex[:10].upper(),
                },
            )
            company = f["base"].get("operating-companies", f["payload"]["operating_company_uid"])
            f["complete"](f["movement"]())
            order = f["new"]()
            order = f["sales"].transition(order["uid"], "confirm", order["version"])
            path.write_text(
                json.dumps(
                    {
                        "product": extra,
                        "company": company,
                        "stock": f["stock"],
                        "locations": f["locations"],
                        "order": order,
                    },
                    default=str,
                )
            )
            subprocess.run(
                ["node", "tests/erp/inventory/browser/inventory.browser.mjs"],
                cwd=args.frontend,
                env={
                    **os.environ,
                    "INVENTORY_BROWSER_FIXTURE": str(path),
                    "INVENTORY_BROWSER_OWNED": str(owned),
                },
                check=True,
            )
        finally:
            for kind, uid in json.loads(owned.read_text()):
                f[
                    {"movements": "moves", "stock-items": "stocks", "locations": "location_uids"}[
                        kind
                    ]
                ].append(UUID(uid))
            try:
                if extra:
                    f["catalog"].store.write(
                        [
                            delete(AuditEvent).where(AuditEvent.record_uid == UUID(extra["uid"])),
                            delete(Item).where(Item.uid == UUID(extra["uid"])),
                        ]
                    )
            finally:
                try:
                    next(fixture)
                except StopIteration:
                    pass


if __name__ == "__main__":
    main()
