"""Companion Finance browser verification with disposable governed local fixtures."""

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from sqlalchemy import insert
from tests.erp.finance.conftest import business, finance_services
from tests.erp.sales.conftest import business as sales_business
from tests.erp.sales.conftest import services as sales_services

from src.erp.finance.metatables import Allocation


def finish(generator):
    try:
        next(generator)
    except StopIteration:
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", type=Path, required=True)
    args = parser.parse_args()
    fixture = business.__wrapped__(finance_services.__wrapped__())
    data = next(fixture)
    sales_fixture = sales_business.__wrapped__(sales_services.__wrapped__())
    sales = next(sales_fixture)
    with TemporaryDirectory(prefix="finance-browser-") as directory:
        source, owned = Path(directory) / "fixture.json", Path(directory) / "owned.json"
        owned.write_text("[]")
        try:
            order = sales["new"]()
            order = sales["sales"].transition(order["uid"], "confirm", 1)
            invoice = data["new"]()
            payment = data["new"]("payments")
            svc = data["service"]
            invoice = svc.transition("invoices", invoice["uid"], "post", 1)
            payment = svc.transition("payments", payment["uid"], "post", 1)
            allocated = svc.allocate(
                {
                    "request_uid": uuid4(),
                    "invoice_uid": invoice["uid"],
                    "payment_uid": payment["uid"],
                    "amount": "1",
                    "expected_invoice_version": invoice["version"],
                    "expected_payment_version": payment["version"],
                }
            )
            svc.store.write(
                [
                    insert(Allocation).values(
                        uid=uuid4(),
                        invoice_uid=UUID(invoice["uid"]),
                        payment_uid=UUID(payment["uid"]),
                        amount="1.00",
                        state="reversed",
                        created_at=datetime.now(timezone.utc),
                        created_by_uid=svc.actor_uid,
                        reversed_at=datetime.now(timezone.utc),
                    )
                    for _ in range(25)
                ]
            )
            source.write_text(
                json.dumps(
                    {
                        "payload": data["payload"],
                        "party_name": data["party"]["name"],
                        "company_name": data["company"]["name"],
                        "currency_name": data["currency"]["name"],
                        "order": order,
                        "history": {
                            "payment_uid": payment["uid"],
                            "allocation_uid": allocated["allocation_uid"],
                        },
                    },
                    default=str,
                )
            )
            subprocess.run(
                ["node", "tests/erp/finance/browser/finance.browser.mjs"],
                cwd=args.frontend,
                env={
                    **os.environ,
                    "FINANCE_BROWSER_FIXTURE": str(source),
                    "FINANCE_BROWSER_OWNED": str(owned),
                },
                check=True,
            )
        finally:
            data["documents"].extend(
                (resource, UUID(uid)) for resource, uid in json.loads(owned.read_text())
            )
            try:
                finish(fixture)
            finally:
                finish(sales_fixture)


if __name__ == "__main__":
    main()
