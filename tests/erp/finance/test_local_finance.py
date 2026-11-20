import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from referencing import Registry, Resource
from sqlalchemy import insert, select

from api.erp.finance.local import create_app
from metatables import MetaTable, upgrade_application
from src.erp.finance.dependencies import Dependencies
from src.erp.finance.errors import FinanceError
from src.erp.finance.metatables import Allocation, AuditEvent, Invoice
from src.erp.finance.service import Service


def posted(business, resource="invoices", **changes):
    row = business["new"](resource, **changes)
    return business["service"].transition(resource, row["uid"], "post", row["version"])


def test_filtered_invoices_share_count_and_page_on_populated_data(business, monkeypatch):
    prefix = f"COLLECTION-{uuid4().hex.upper()}"
    business["new"]("invoices", name=f"{prefix}-DRAFT")
    posted(business, name=f"{prefix}-FIRST")
    newest = posted(business, name=f"{prefix}-SECOND")
    service = business["service"]
    read = service.store.read
    calls = []

    def measured(statement, **kwargs):
        calls.append(statement)
        return read(statement, **kwargs)

    monkeypatch.setattr(service.store, "read", measured)
    page = service.collection("invoices", search=prefix, state="posted", page_size=1)
    end = service.collection("invoices", search=prefix, state="posted", page_size=1, page_index=2)
    assert len(calls) == 2
    assert [item["uid"] for item in page["items"]] == [newest["uid"]]
    assert page["pageInfo"]["totalItems"] == end["pageInfo"]["totalItems"] == 2
    assert page["pageInfo"]["hasNextPage"] and end["items"] == []


def request(invoice, payment, amount="120", **changes):
    return {
        "request_uid": uuid4(),
        "invoice_uid": invoice["uid"],
        "payment_uid": payment["uid"],
        "amount": amount,
        "expected_invoice_version": invoice["version"],
        "expected_payment_version": payment["version"],
        **changes,
    }


def test_balanced_postings_allocation_and_reversal(business):
    svc = business["service"]
    invoice = posted(business)
    payment = posted(business, "payments")
    assert (
        invoice["net_total"] == "100.00"
        and invoice["tax_total"] == "20.00"
        and invoice["total"] == "120.00"
    )
    for row in [invoice, payment]:
        assert sum(Decimal(p["amount"]) for p in row["postings"]) == 0
    result = svc.allocate(request(invoice, payment, "40"))
    assert (
        result["invoice"]["remaining"] == "80.00"
        and result["invoice"]["payment_status"] == "partial"
    )
    with pytest.raises(FinanceError) as blocked:
        svc.transition(
            "invoices", invoice["uid"], "void", result["invoice"]["version"], "Fixture reversal"
        )
    assert blocked.value.code == "allocated"
    cleared = svc.reverse_allocation(
        result["allocation_uid"], result["invoice"]["version"], result["payment"]["version"]
    )
    assert cleared["invoice"]["remaining"] == "120.00"
    final = svc.allocate(request(cleared["invoice"], cleared["payment"]))
    assert final["invoice"]["payment_status"] == "paid"
    cleared = svc.reverse_allocation(
        final["allocation_uid"], final["invoice"]["version"], final["payment"]["version"]
    )
    for resource in ["invoices", "payments"]:
        row = cleared["invoice" if resource == "invoices" else "payment"]
        void = svc.transition(resource, row["uid"], "void", row["version"], "Recorded in error")
        assert (
            void["state"] == "void"
            and Decimal(void["remaining"]) == 0
            and void["payment_status"] == "void"
        )
        roles = {p["account_role"] for p in void["postings"]}
        for role in roles:
            assert (
                sum(Decimal(p["amount"]) for p in void["postings"] if p["account_role"] == role)
                == 0
            )
        with pytest.raises(FinanceError):
            svc.transition(resource, row["uid"], "post", void["version"])


def test_vendor_flow_and_immutable_posted_terms(business):
    svc = business["service"]
    invoice = posted(business, kind="vendor")
    payment = posted(business, "payments", kind="vendor")
    assert {r["account_role"]: r["amount"] for r in invoice["postings"]} == {
        "expense": "100.00",
        "tax_recoverable": "20.00",
        "payable": "-120.00",
    }
    assert svc.allocate(request(invoice, payment))["invoice"]["remaining"] == "0.00"
    with pytest.raises(FinanceError):
        svc.save(
            "invoices",
            svc.draft_payload("invoices", invoice),
            uid=invoice["uid"],
            expected_version=invoice["version"],
        )


def test_concurrent_allocations_and_atomic_rollback(business):
    svc = business["service"]
    invoice = posted(business)
    payment = posted(business, "payments")

    def allocate(_):
        try:
            return svc.allocate(request(invoice, payment, "80"))
        except FinanceError as error:
            return error

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(allocate, range(2)))
    assert sum(isinstance(row, dict) for row in results) == 1
    assert next(row for row in results if isinstance(row, FinanceError)).status == 409
    inv = svc.get("invoices", invoice["uid"])
    pay = svc.get("payments", payment["uid"])
    assert inv["allocated"] == pay["allocated"] == "80.00"
    with pytest.raises(FinanceError) as exceeds:
        svc.allocate(request(inv, pay, "41"))
    assert exceeds.value.code == "insufficient_balance"
    before = len(inv["allocations"])
    with pytest.raises(FinanceError):
        svc.transact(
            [
                svc.guard("invoices", inv, inv["version"], {"allocated": "1"}),
                svc.audit("invoices", inv["uid"], "bad-test", 99, ["allocated"]),
                insert(Invoice).values(uid=uuid4()),
            ]
        )
    assert svc.get("invoices", invoice["uid"])["allocated"] == "80.00"
    assert len(svc.get("invoices", invoice["uid"])["allocations"]) == before
    assert not svc.store.read(
        select(AuditEvent.__table__).where(
            AuditEvent.record_uid == UUID(inv["uid"]), AuditEvent.version == 99
        )
    )


@pytest.mark.parametrize(
    "line",
    [
        {"quantity": "0"},
        {"unit_price": 1.2},
        {"unit_price": "-1"},
        {"discount": "101"},
        {"tax_rate": "NaN"},
        {"tax_rate": "100.01"},
    ],
)
def test_invalid_decimal_inputs(business, line):
    with pytest.raises(ValidationError):
        business["new"](
            lines=[{"description": "Fixture", "quantity": "1", "unit_price": "20", **line}]
        )


def test_precision_dates_permissions_and_mismatch(business):
    svc = business["service"]
    with pytest.raises(FinanceError) as precision:
        business["new"]("payments", amount="0.001")
    assert precision.value.code == "precision"
    with pytest.raises(ValidationError):
        business["new"](due_date=date.today() - timedelta(days=1))
    future = business["new"]("payments", document_date=date.today() + timedelta(days=1))
    with pytest.raises(FinanceError) as early:
        svc.transition("payments", future["uid"], "post", 1)
    assert early.value.code == "future_date"
    invoice = posted(business)
    wrong = posted(business, "payments", kind="vendor")
    with pytest.raises(FinanceError) as mismatch:
        svc.allocate(request(invoice, wrong))
    assert mismatch.value.code == "mismatch"
    writer = Service(svc.store, svc.actor_uid, {"finance.read", "finance.write"}, svc.dependencies)
    with pytest.raises(FinanceError) as denied:
        writer.transition("payments", wrong["uid"], "void", wrong["version"], "Test")
    assert denied.value.status == 403
    zero = business["new"](lines=[])
    with pytest.raises(FinanceError):
        svc.transition("invoices", zero["uid"], "post", 1)


def test_sales_invoice_atomic_trace_and_independence(business, monkeypatch):
    from tests.erp.sales.conftest import business as sales_business
    from tests.erp.sales.conftest import services as sales_services

    from src.erp.finance.sales_integration import SalesPort
    from src.erp.sales.errors import SalesError

    source = sales_business.__wrapped__(sales_services.__wrapped__())
    context = next(source)
    svc = business["service"]
    original = svc.dependencies
    svc.dependencies = Dependencies(business["base"], lambda: SalesPort(context["sales"]))
    try:
        order = context["new"]()
        order = context["sales"].transition(order["uid"], "confirm", 1)
        uid = uuid4()
        business["documents"].append(("invoices", uid))
        args = {
            "request_uid": uid,
            "order_uid": order["uid"],
            "expected_order_version": order["version"],
            "name": "INV-" + uuid4().hex[:12].upper(),
            "document_date": date.today(),
            "due_date": date.today(),
            "tax_rate": "20",
        }
        invoice = svc.from_sales(args)
        assert invoice["source_order_uid"] == order["uid"]
        assert (
            invoice["net_total"] == order["net_total"]
            and invoice["lines"][0]["source"]["line_uid"] == order["lines"][0]["uid"]
        )
        linked = context["sales"].get(order["uid"])
        assert f"finance:{uid}" in linked["downstream"]
        with pytest.raises(SalesError):
            context["sales"].transition(order["uid"], "cancel", linked["version"])
        failed_uid = uuid4()
        business["documents"].append(("invoices", failed_uid))
        with pytest.raises(FinanceError):
            svc.from_sales(
                {
                    **args,
                    "request_uid": failed_uid,
                    "expected_order_version": linked["version"],
                    "name": "INV-" + uuid4().hex[:12].upper(),
                }
            )
        unchanged = context["sales"].get(order["uid"])
        assert (
            unchanged["version"] == linked["version"]
            and unchanged["downstream"] == linked["downstream"]
        )
        changed = svc.draft_payload("invoices", invoice)
        changed["lines"][0]["quantity"] = "99"
        with pytest.raises(FinanceError) as immutable:
            svc.save("invoices", changed, uid=uid, expected_version=1)
        assert immutable.value.code == "source_terms"
        invoice = svc.transition("invoices", uid, "post", 1)
        payment = posted(
            business,
            "payments",
            party_uid=order["customer_uid"],
            operating_company_uid=order["operating_company_uid"],
            currency_uid=order["currency_uid"],
            amount=invoice["total"],
        )
        assert (
            svc.allocate(request(invoice, payment, invoice["total"]))["invoice"]["payment_status"]
            == "paid"
        )
    finally:
        svc.dependencies = original
        try:
            next(source)
        except StopIteration:
            pass
    assert posted(business)["state"] == "posted"


def test_migration_http_contracts_and_restart(business):
    row = business["new"]()
    identifiers = [
        "erp_base.alembic_version",
        "erp_catalog.alembic_version",
        "erp_sales.alembic_version",
        "mainsequence_crm.alembic_version",
    ]
    before = {
        r.identifier: r.alembic_revision for r in MetaTable.filter(identifier__in=identifiers)
    }
    assert upgrade_application("src.erp.finance.migrations:migration")["revision"] == "0002"
    assert before == {
        r.identifier: r.alembic_revision for r in MetaTable.filter(identifier__in=identifiers)
    }
    code = """from metatables import configure_local_client
configure_local_client()
from src.erp.finance.store import Store
from src.erp.finance.metatables import Invoice
from api.erp.finance.main import create_app
from sqlalchemy import select
from uuid import UUID
import sys
assert not any(k.startswith(('src.erp.crm','src.erp.sales','src.erp.catalog')) for k in sys.modules)
assert not any(r.path.startswith('/api/finance') for r in create_app(enabled=False).routes)
print(Store(local_only=True).read(select(Invoice.__table__).where(Invoice.uid==UUID(sys.argv[1])))[0]['uid'])
"""
    assert (
        subprocess.run(
            [sys.executable, "-c", code, row["uid"]], capture_output=True, text=True, check=True
        ).stdout.strip()
        == row["uid"]
    )
    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 51000)
    ) as client:
        assert client.get("/api/finance/v1/ready/").json()["local"] is True
        root = Path("tests/erp/finance/contracts/sdk-0.5.19/schemas")
        schemas = [json.loads(p.read_text()) for p in root.glob("*.json")]
        registry = Registry().with_resources(
            [(s["$id"], Resource.from_contents(s)) for s in schemas]
        )
        for resource in ["invoices", "payments"]:
            for suffix, name in [
                ("", "resource-collection-v1"),
                ("discovery/", "resource-discovery-v1"),
            ]:
                response = client.get(f"/api/finance/v1/{resource}/{suffix}")
                assert response.status_code == 200, response.text
                Draft202012Validator(
                    json.loads((root / (name + ".schema.json")).read_text()), registry=registry
                ).validate(response.json())
        assert (
            client.get("/api/finance/v1/ready/", headers={"x-user-uid": str(uuid4())}).status_code
            == 401
        )
        assert (
            client.get(
                "/api/finance/v1/ready/", headers={"Origin": "https://outside.example"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/finance/v1/invoices/{row['uid']}/post/", json={"expected_version": 0}
            ).status_code
            == 422
        )


def test_older_allocation_remains_accessible_and_reversible(business):
    from datetime import datetime, timezone

    svc = business["service"]
    invoice, payment = posted(business), posted(business, "payments")
    first = svc.allocate(request(invoice, payment, "1"))
    # Owned fixture history: later reversed events must not hide the older active allocation.
    history = [
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
        for _ in range(100)
    ]
    for offset in range(0, len(history), 25):
        svc.store.write(history[offset : offset + 25])
    pages = [svc.allocation_collection("payments", payment["uid"], page_index=i) for i in range(5)]
    assert pages[0]["pageInfo"]["totalItems"] == 101
    ids = [row["uid"] for page in pages for row in page["items"]]
    assert len(ids) == len(set(ids)) == 101
    assert pages[-1]["items"][0]["uid"] == first["allocation_uid"]
    assert pages[-1]["items"][0]["invoice_reference"] == invoice["name"]
    result = svc.reverse_allocation(
        first["allocation_uid"], first["invoice"]["version"], first["payment"]["version"]
    )
    assert result["invoice"]["remaining"] == result["payment"]["remaining"] == "120.00"


def test_source_invoice_due_date_is_validated_before_handoff():
    from src.erp.finance.schemas import FromSalesInput

    with pytest.raises(ValidationError):
        FromSalesInput(
            request_uid=uuid4(),
            order_uid=uuid4(),
            expected_order_version=1,
            name="INVALID-DATE",
            document_date=date.today(),
            due_date=date.today() - timedelta(days=1),
        )
