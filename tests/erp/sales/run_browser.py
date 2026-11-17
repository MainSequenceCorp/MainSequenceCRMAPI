"""Run the paired frontend browser suite with locally governed, owned fixtures."""

import argparse
import json
import os
import subprocess
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from tests.erp.sales.conftest import business, services


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", type=Path, required=True)
    args = parser.parse_args()
    fixture = business.__wrapped__(services.__wrapped__())
    data = next(fixture)
    with TemporaryDirectory(prefix="sales-browser-") as directory:
        source, owned = Path(directory) / "fixture.json", Path(directory) / "owned.json"
        c = data["currency"]
        source.write_text(
            json.dumps(
                {
                    "payload": data["payload"],
                    "customer_name": data["base"].get("parties", data["payload"]["customer_uid"])[
                        "name"
                    ],
                    "company_name": data["base"].get(
                        "operating-companies", data["payload"]["operating_company_uid"]
                    )["name"],
                    "currency_name": c["name"],
                    "item_name": data["item"]["name"],
                    "expected_total": str(
                        Decimal("33.750").quantize(
                            Decimal(1).scaleb(-c["minor_units"]),
                            rounding=ROUND_HALF_EVEN
                            if c["rounding"] == "half_even"
                            else ROUND_HALF_UP,
                        )
                    ),
                }
            )
        )
        owned.write_text("[]")
        try:
            subprocess.run(
                ["node", "tests/erp/sales/browser/sales.browser.mjs"],
                cwd=args.frontend,
                env={
                    **os.environ,
                    "SALES_BROWSER_FIXTURE": str(source),
                    "SALES_BROWSER_OWNED": str(owned),
                },
                check=True,
            )
        finally:
            data["orders"].extend(UUID(uid) for uid in set(json.loads(owned.read_text())))
            try:
                next(fixture)
            except StopIteration:
                pass


if __name__ == "__main__":
    main()
