"""Run the companion browser against owned Local SQLite fixtures and clean exact UUIDs."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from tests.erp.inventory.conftest import inventory_services, stock
from tests.erp.purchasing.conftest import purchase


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", type=Path, required=True)
    args = parser.parse_args()
    parent = stock.__wrapped__(inventory_services.__wrapped__())
    f = next(parent)
    child = purchase.__wrapped__(f)
    p = None
    try:
        p = next(child)
        company = p["base"].get(
            "operating-companies", p["purchase_payload"]["operating_company_uid"]
        )
        supplier = p["base"].get("parties", p["purchase_payload"]["supplier_uid"])
        with TemporaryDirectory(prefix="purchasing-browser-") as folder:
            path = Path(folder) / "fixture.json"
            owned = Path(folder) / "owned.json"
            owned.write_text("[]")
            fixture = {
                "product": p["item"],
                "service": p["service_item"],
                "company": company,
                "supplier": supplier,
                "currency": p["currency"],
                "stock": p["stock"],
                "locations": p["locations"],
            }
            path.write_text(json.dumps(fixture, default=str))
            Path("/tmp/purchasing-browser-current-fixture.json").write_text(
                json.dumps(fixture, default=str)
            )
            try:
                subprocess.run(
                    ["node", "tests/erp/purchasing/browser/purchasing.browser.mjs"],
                    cwd=args.frontend,
                    env={
                        **os.environ,
                        "PURCHASING_BROWSER_FIXTURE": str(path),
                        "PURCHASING_BROWSER_OWNED": str(owned),
                    },
                    check=True,
                )
            finally:
                for kind, uid in json.loads(owned.read_text()):
                    p[kind].append(UUID(uid))
    finally:
        try:
            if p is not None:
                try:
                    next(child)
                except StopIteration:
                    pass
        finally:
            try:
                next(parent)
            except StopIteration:
                pass


if __name__ == "__main__":
    main()
