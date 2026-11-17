"""Exercise the companion against disposable owned local fixtures, then clean exact IDs."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from tests.erp.inventory.conftest import inventory_services, stock
from tests.erp.manufacturing.conftest import manufacturing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", type=Path, required=True)
    args = parser.parse_args()
    parent = stock.__wrapped__(inventory_services.__wrapped__())
    f = next(parent)
    child = manufacturing.__wrapped__(f)
    p = None
    try:
        p = next(child)
        p["seed"]()
        fixture = {key: p[key] for key in ["item", "output", "locations", "production_location"]}
        fixture["company"] = p["base"].get(
            "operating-companies", p["payload"]["operating_company_uid"]
        )
        with TemporaryDirectory(prefix="manufacturing-browser-") as folder:
            path = Path(folder) / "fixture.json"
            owned = Path(folder) / "owned.json"
            owned.write_text("[]")
            path.write_text(json.dumps(fixture, default=str))
            try:
                subprocess.run(
                    ["node", "tests/erp/manufacturing/browser/manufacturing.browser.mjs"],
                    cwd=args.frontend,
                    env={
                        **os.environ,
                        "MANUFACTURING_BROWSER_FIXTURE": str(path),
                        "MANUFACTURING_BROWSER_OWNED": str(owned),
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
