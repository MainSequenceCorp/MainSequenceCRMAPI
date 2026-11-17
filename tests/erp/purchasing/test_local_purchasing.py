import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from metatables import upgrade_application
from src.erp.finance.errors import FinanceError
from src.erp.finance.schemas import InvoiceInput
from src.erp.purchasing.dependencies import Dependencies
from src.erp.purchasing.errors import PurchasingError
from src.erp.purchasing.metatables import MODELS
from src.erp.purchasing.schemas import VersionInput
from src.erp.purchasing.service import Service


def error(status, call):
    with pytest.raises(PurchasingError) as e:
        call()
    assert e.value.status == status, e.value.message


def test_purchase_physical_receipt_bill_source_lock_return(purchase):
    f = purchase
    s = f["purchasing"]
    inv = f["service"]
    fin = f["finance"]
    row = f["new_purchase"]()
    assert row["net_total"] == "33.75" and row["lines"][0]["snapshot"]["stock_quantity"] == "3"
    row = s.transition(row["uid"], "rfq", row["version"])
    row = s.transition(row["uid"], "confirm", row["version"])
    error(409, lambda: f["bill_purchase"](row))
    row = f["receive_purchase"](row)
    move_uid = row["receipts"][0]["movement_uid"]
    assert inv.get("movements", move_uid)["snapshot"]["purchase_order_uid"] == row["uid"]
    error(409, lambda: f["receive_purchase"](row))
    error(409, lambda: s.transition(row["uid"], "cancel", row["version"]))
    f["complete"](inv.get("movements", move_uid))
    row = s.transition(row["uid"], "close", row["version"])
    row = f["bill_purchase"](row, tax_rate="20")
    bill = fin.get("invoices", row["bill_uid"])
    assert (
        bill["kind"] == "vendor"
        and bill["source_purchase_order_uid"] == row["uid"]
        and bill["source_order_uid"] is None
    )
    assert bill["net_total"] == "33.75" and bill["total"] == "40.50"
    assert bill["lines"][0]["source"]["purchase_order_uid"] == row["uid"]
    payload = {k: bill[k] for k in InvoiceInput.model_fields if k != "lines"}
    payload["lines"] = [
        {k: line[k] for k in ("description", "quantity", "unit_price", "discount", "tax_rate")}
        for line in bill["lines"]
    ]
    changed = {**payload, "lines": [{**payload["lines"][0], "quantity": "4"}]}
    with pytest.raises(FinanceError):
        fin.save("invoices", changed, uid=bill["uid"], expected_version=bill["version"])
    bill = fin.save(
        "invoices",
        {**payload, "notes": "Reviewed"},
        uid=bill["uid"],
        expected_version=bill["version"],
    )
    assert bill["source_purchase_order_uid"] == row["uid"]
    error(409, lambda: f["bill_purchase"](row))
    move = inv.get("movements", move_uid)
    uid = uuid4()
    f["moves"].append(uid)
    inv.reverse(
        move_uid,
        {"request_uid": uid, "expected_version": move["version"], "reason": "Supplier return"},
    )
    status = s.fulfillment(row["uid"])
    assert not status["all_received"] and status["items"][0]["state"] == "returned"
    assert fin.get("invoices", bill["uid"])["state"] == "draft"


def test_service_acceptance_independent_and_permissions(purchase):
    f = purchase
    s = f["purchasing"]
    item = f["service_item"]
    row = f["confirm_purchase"](
        lines=[{"item_uid": item["uid"], "quantity": "1", "unit_price": "50"}]
    )
    independent = Service(
        s.store, s.actor_uid, s.capabilities, Dependencies(f["base"], f["catalog"])
    )
    error(503, lambda: independent.dependencies.inventory())
    row = independent.accept(
        row["uid"],
        row["lines"][0]["uid"],
        {"expected_version": row["version"], "request_uid": uuid4(), "reason": "Work checked"},
    )
    assert independent.fulfillment(row["uid"])["all_received"]
    error(
        503,
        lambda: independent.bill(
            row["uid"],
            {
                "expected_version": row["version"],
                "request_uid": uuid4(),
                "name": "NONE",
                "document_date": "2026-11-17",
                "due_date": "2026-12-17",
            },
        ),
    )
    row = independent.revoke(
        row["uid"],
        row["lines"][0]["uid"],
        {"expected_version": row["version"], "reason": "Acceptance withdrawn"},
    )
    assert not independent.fulfillment(row["uid"])["all_received"]
    error(409, lambda: independent.transition(row["uid"], "close", row["version"]))
    reader = Service(s.store, s.actor_uid, {"purchasing.read"}, s.dependencies)
    error(
        403,
        lambda: reader.accept(
            row["uid"],
            row["lines"][0]["uid"],
            {"expected_version": row["version"], "request_uid": uuid4(), "reason": "Denied"},
        ),
    )
    row = f["confirm_purchase"](
        lines=[{"item_uid": item["uid"], "quantity": "1", "unit_price": "50"}]
    )
    row = independent.accept(
        row["uid"],
        row["lines"][0]["uid"],
        {"expected_version": row["version"], "request_uid": uuid4(), "reason": "Accepted"},
    )
    assert independent.transition(row["uid"], "close", row["version"])["state"] == "closed"


def test_stale_atomic_receipt_and_concurrent_acceptance(purchase, monkeypatch):
    f = purchase
    s = f["purchasing"]
    inv = f["service"]
    row = f["confirm_purchase"]()
    original = inv.plan_purchase_receipt

    def racing(order, line, payload):
        uid, steps = original(order, line, payload)
        s.transition(row["uid"], "cancel", row["version"])
        return uid, steps

    monkeypatch.setattr(inv, "plan_purchase_receipt", racing)
    error(409, lambda: f["receive_purchase"](row))
    assert s.get(row["uid"])["receipts"] == []
    from src.erp.inventory.errors import InventoryError

    with pytest.raises(InventoryError) as e:
        inv.get("movements", f["moves"][-1])
    assert e.value.status == 404
    monkeypatch.setattr(inv, "plan_purchase_receipt", original)
    item = f["service_item"]
    row = f["confirm_purchase"](
        lines=[{"item_uid": item["uid"], "quantity": "1", "unit_price": "1"}]
    )
    barrier = Barrier(2)

    def accept():
        barrier.wait()
        try:
            return s.accept(
                row["uid"],
                row["lines"][0]["uid"],
                {"expected_version": row["version"], "request_uid": uuid4(), "reason": "Observed"},
            )["version"]
        except PurchasingError as e:
            return e.status

    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(lambda _: accept(), range(2)))
    assert sorted(outcomes) == [row["version"] + 1, 409]
    assert len(s.get(row["uid"])["receipts"]) == 1


def test_bill_return_race_rolls_back_all_claims(purchase, monkeypatch):
    f = purchase
    s = f["purchasing"]
    inv = f["service"]
    fin = f["finance"]
    row = f["receive_purchase"](f["confirm_purchase"]())
    move = f["complete"](inv.get("movements", row["receipts"][0]["movement_uid"]))
    original = fin.plan_from_purchase

    def racing(order, payload):
        uid, plan = original(order, payload)
        ret = uuid4()
        f["moves"].append(ret)
        inv.reverse(
            move["uid"],
            {
                "request_uid": ret,
                "expected_version": move["version"],
                "reason": "Race with billing",
            },
        )
        return uid, plan

    monkeypatch.setattr(fin, "plan_from_purchase", racing)
    error(409, lambda: f["bill_purchase"](row))
    assert s.get(row["uid"])["bill_uid"] is None
    with pytest.raises(FinanceError) as e:
        fin.get("invoices", f["purchase_bills"][-1])
    assert e.value.status == 404


def test_unit_conversion_precision_lifecycle_and_policy(purchase):
    f = purchase
    s = f["purchasing"]
    catalog = f["catalog"]
    from src.erp.catalog.schemas import ItemInput

    item = f["item"]
    unit = catalog.save(
        "units",
        {
            "name": "Purchase dozen",
            "code": "DOZ-" + uuid4().hex[:12].upper(),
            "group_uid": catalog.get("units", item["unit_uid"])["group_uid"],
            "factor": "12",
            "rounding_increment": "0.01",
        },
    )
    f["extra_units"].append(UUID(unit["uid"]))
    item = catalog.save(
        "items",
        {
            **{k: item[k] for k in ItemInput.model_fields},
            "code": "CONV-" + uuid4().hex[:12].upper(),
            "purchase_unit_uid": unit["uid"],
        },
    )
    f["extra_items"].append(item["uid"])
    f["purchase_payload"]["lines"][0]["item_uid"] = item["uid"]
    row = f["new_purchase"](lines=[{"item_uid": item["uid"], "quantity": "2", "unit_price": "10"}])
    assert row["lines"][0]["snapshot"]["stock_quantity"] == "24" and row["net_total"] == "20.00"
    error(
        422,
        lambda: f["new_purchase"](
            lines=[{"item_uid": item["uid"], "quantity": "0.0001", "unit_price": "1"}]
        ),
    )
    row = s.transition(row["uid"], "rfq", row["version"])
    error(409, lambda: s.transition(row["uid"], "confirm", 1))
    row = s.transition(row["uid"], "reopen", row["version"])
    row = s.transition(row["uid"], "cancel", row["version"])
    assert s.transition(row["uid"], "reopen", row["version"])["state"] == "draft"
    item = catalog.save(
        "items",
        {**{k: item[k] for k in ItemInput.model_fields}, "purchasable": False},
        uid=item["uid"],
        expected_version=item["version"],
    )
    error(422, lambda: f["new_purchase"]())
    with pytest.raises(ValidationError):
        VersionInput(expected_version=True)
    with pytest.raises(ValidationError):
        s.save(
            {**f["purchase_payload"], "name": "FORGED", "state": "confirmed"}, request_uid=uuid4()
        )


def test_runtime_contracts_and_independent_import(purchase):
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    from api.erp.purchasing.local import create_app

    f = purchase
    row = f["new_purchase"]()
    assert upgrade_application("src.erp.purchasing.migrations:migration")["revision"] == "0001"
    assert {m.__metatable_namespace__ for m in MODELS} == {"erp-purchasing"}
    code = """import sys
from metatables import configure_local_client
configure_local_client()
from src.erp.purchasing.store import Store
from src.erp.purchasing.metatables import Order
from api.erp.purchasing.main import create_app
from sqlalchemy import select
from uuid import UUID
assert 'src.erp.inventory.service' not in sys.modules and 'src.erp.finance.service' not in sys.modules
assert not any(r.path.startswith('/api/purchasing') for r in create_app(enabled=False).routes)
print(Store(local_only=True).read(select(Order.__table__).where(Order.uid==UUID(sys.argv[1])))[0]['uid'])
"""
    assert row["uid"] in subprocess.check_output(
        [".venv/bin/python", "-c", code, row["uid"]], text=True
    )
    schemas = [
        json.loads(p.read_text())
        for p in Path("tests/erp/purchasing/contracts/sdk-0.5.19/schemas").glob("*.json")
    ]
    reg = Registry().with_resources([(x["$id"], Resource.from_contents(x)) for x in schemas])
    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 50000)
    ) as client:
        assert client.get("/api/purchasing/v1/ready/").json()["local"] is True
        for suffix, name in [("", "resource-collection"), ("discovery/", "resource-discovery")]:
            response = client.get("/api/purchasing/v1/orders/" + suffix)
            assert response.status_code == 200, response.text
            schema = next(x for x in schemas if name in x["$id"])
            Draft202012Validator(schema, registry=reg).validate(response.json())
        for headers in [
            {"x-user-uid": str(uuid4())},
            {"Origin": "https://external.example"},
            {"Host": "external.example"},
        ]:
            assert client.get("/api/purchasing/v1/ready/", headers=headers).status_code in (
                401,
                403,
            )
        assert (
            client.post(
                "/api/purchasing/v1/orders/" + row["uid"] + "/confirm/",
                json={"expected_version": True},
            ).status_code
            == 422
        )


def test_owner_permissions_sources_and_unreceived_returns(purchase, monkeypatch):
    from src.erp.finance.service import Service as FinanceService
    from src.erp.inventory.service import Service as InventoryService
    from src.erp.purchasing.integrations import OwnerPort
    from src.erp.purchasing.store import Store

    f = purchase
    s = f["purchasing"]
    inv = f["service"]
    fin = f["finance"]
    row = f["confirm_purchase"]()
    denied = InventoryService(inv.store, inv.actor_uid, {"inventory.read"}, inv.dependencies)
    monkeypatch.setattr(s.dependencies, "inventory_factory", lambda: OwnerPort(denied))
    error(403, lambda: f["receive_purchase"](row))
    assert not s.get(row["uid"])["receipts"]
    monkeypatch.setattr(s.dependencies, "inventory_factory", lambda: OwnerPort(inv))
    row = f["receive_purchase"](row)
    move = f["complete"](inv.get("movements", row["receipts"][0]["movement_uid"]))
    denied_finance = FinanceService(fin.store, fin.actor_uid, {"finance.read"}, fin.dependencies)
    monkeypatch.setattr(s.dependencies, "finance_factory", lambda: OwnerPort(denied_finance))
    error(403, lambda: f["bill_purchase"](row))
    assert s.get(row["uid"])["bill_uid"] is None
    assert inv.get("movements", move["uid"])["version"] == move["version"]
    monkeypatch.setattr(s.dependencies, "finance_factory", lambda: OwnerPort(fin))
    uid = uuid4()
    f["moves"].append(uid)
    inv.reverse(
        move["uid"],
        {
            "request_uid": uid,
            "expected_version": move["version"],
            "reason": "Returned before billing",
        },
    )
    error(409, lambda: f["bill_purchase"](row))
    assert s.get(row["uid"])["bill_uid"] is None
    fake = type(
        "DifferentOwner", (), {"store": type("Source", (), {"data_source_uid": str(uuid4())})()}
    )()
    error(503, lambda: s.same_source(fake))
    import src.erp.purchasing.store as store_module

    current = Store(local_only=True)
    assert current.data_source_uid == s.store.data_source_uid
    monkeypatch.setattr(store_module, "require_local_runtime", lambda: str(uuid4()))
    with pytest.raises(RuntimeError):
        current.write([])
