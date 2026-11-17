"""Exercise merchant and separate customer origins with owned disposable local data."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from tests.erp.commerce.conftest import commerce
from tests.erp.sales.conftest import business, services


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", type=Path, required=True)
    args = parser.parse_args()
    parent = business.__wrapped__(services.__wrapped__())
    f = next(parent)
    child = commerce.__wrapped__(f)
    p = None
    try:
        p = next(child)
        fixture = {
            "item": p["item"],
            "currency": p["currency"],
            "company": p["base"].get("operating-companies", p["payload"]["operating_company_uid"]),
            "customer": p["base"].get("parties", p["payload"]["customer_uid"]),
        }
        with TemporaryDirectory(prefix="commerce-browser-") as folder:
            path = Path(folder) / "fixture.json"
            owned = Path(folder) / "owned.json"
            owned.write_text("[]")
            path.write_text(json.dumps(fixture, default=str))
            try:
                subprocess.run(
                    ["node", "tests/erp/commerce/browser/commerce.browser.mjs"],
                    cwd=args.frontend,
                    env={
                        **os.environ,
                        "COMMERCE_BROWSER_FIXTURE": str(path),
                        "COMMERCE_BROWSER_OWNED": str(owned),
                    },
                    check=True,
                )
            finally:
                for kind, uid in json.loads(owned.read_text()):
                    p["commerce_owned"][kind].append(UUID(uid))
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
