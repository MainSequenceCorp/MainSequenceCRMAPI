import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from referencing import Registry, Resource
from sqlalchemy import select

from api.erp.inventory.local import create_app
from metatables import upgrade_application
from src.erp.finance.dependencies import Dependencies as FinanceDependencies
from src.erp.finance.service import Service as FinanceService
from src.erp.inventory.dependencies import Dependencies
from src.erp.inventory.errors import InventoryError
from src.erp.inventory.integrations import OwnerPort
from src.erp.inventory.metatables import Entry, Move
from src.erp.inventory.schemas import MovementCreate, VersionInput
from src.erp.inventory.service import Service


def error(code, fn):
    with pytest.raises(InventoryError) as result:
        fn()
    assert result.value.status == code, result.value.message


def total(svc, stock_uid, loc):
    return svc.balance(stock_uid, loc["uid"])


def test_receipt_transfer_reservation_delivery_return_reconciliation(stock):
    f = stock
    s = f["service"]
    p = f["stock"]
    loc = f["locations"]
    received = f["complete"](f["movement"]())
    assert received["net_value"] == "25.00"
    transfer = f["movement"]("a", "b", "4")
    ready = s.transition(transfer["uid"], "prepare", 1)
    assert total(s, p["uid"], loc["a"])["reserved_ticks"] == 400
    competing = f["movement"]("a", "customer", "7")
    error(409, lambda: s.transition(competing["uid"], "prepare", 1))
    moved = s.transition(ready["uid"], "complete", ready["version"])
    assert moved["net_value"] == "0.00"
    assert sorted(e["quantity_ticks"] for e in moved["entries"]) == [-400, 400]
    delivery = f["complete"](f["movement"]("b", "customer", "3"))
    assert delivery["net_value"] == "-7.50"
    uid = uuid4()
    f["moves"].append(uid)
    returned = s.reverse(
        delivery["uid"],
        {"request_uid": uid, "expected_version": delivery["version"], "reason": "Goods returned"},
    )
    assert returned["net_value"] == "7.50"
    assert total(s, p["uid"], loc["b"])["on_hand_ticks"] == 400
    error(
        409,
        lambda: s.reverse(
            delivery["uid"],
            {
                "request_uid": uuid4(),
                "expected_version": s.get("movements", delivery["uid"])["version"],
                "reason": "Duplicate",
            },
        ),
    )
    error(409, lambda: s.transition(received["uid"], "cancel", received["version"]))
    for location in [loc["a"], loc["b"]]:
        balance = total(s, p["uid"], location)
        entries = s.store.read(
            select(Entry.quantity_ticks).where(
                Entry.stock_item_uid == UUID(p["uid"]), Entry.location_uid == UUID(location["uid"])
            )
        )
        assert sum(e["quantity_ticks"] for e in entries) == balance["on_hand_ticks"]
    cancel = f["movement"]("a", "customer", "6")
    ready = s.transition(cancel["uid"], "prepare", 1)
    s.transition(cancel["uid"], "cancel", ready["version"])
    assert total(s, p["uid"], loc["a"])["reserved_ticks"] == 0
    error(
        409, lambda: s.archive("stock-items", p["uid"], s.get("stock-items", p["uid"])["version"])
    )
    error(422, lambda: f["movement"](quantity="0.001"))
    error(422, lambda: f["movement"]("supplier", "customer"))
    error(422, lambda: f["movement"]("a", "a"))
    error(422, lambda: f["movement"]("adjustment", "a", reason=""))
    with pytest.raises(ValidationError):
        VersionInput(expected_version=True)
    with pytest.raises(ValidationError):
        MovementCreate(
            request_uid=uuid4(),
            name="forged",
            stock_item_uid=p["uid"],
            source_uid=loc["a"]["uid"],
            destination_uid=loc["b"]["uid"],
            quantity="1",
            state="done",
        )


def test_competing_reservations_and_partial_plan_rollback(stock):
    f = stock
    s = f["service"]
    f["complete"](f["movement"](quantity="5"))
    moves = [f["movement"]("a", "customer", "4") for _ in range(2)]
    barrier = Barrier(2)

    class RacingStore:
        data_source_uid = s.store.data_source_uid

        def read(self, *args, **kwargs):
            return s.store.read(*args, **kwargs)

        def write(self, statements):
            barrier.wait(timeout=10)
            return s.store.write(statements)

    racing = Service(RacingStore(), s.actor_uid, s.capabilities, s.dependencies)

    def reserve(move):
        try:
            return racing.transition(move["uid"], "prepare", 1)
        except InventoryError as exc:
            return exc.status

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(reserve, moves))
    assert sum(isinstance(row, dict) for row in results) == 1
    assert 409 in results
    assert total(s, f["stock"]["uid"], f["locations"]["a"])["reserved_ticks"] == 400
    before = s.get("movements", moves[0]["uid"])
    steps = s.plan_movement(
        {
            "request_uid": uuid4(),
            "name": "rollback",
            "stock_item_uid": f["stock"]["uid"],
            "source_uid": f["locations"]["supplier"]["uid"],
            "destination_uid": f["locations"]["a"]["uid"],
            "quantity": "1",
        }
    )[1]
    # Append a guaranteed stale guard after earlier version changes: all roll back.
    stock_before = s.get("stock-items", f["stock"]["uid"])
    error(409, lambda: s.transact([*steps, s.guard(Move, before, {}, expected=999999)]))
    assert s.get("stock-items", f["stock"]["uid"])["version"] == stock_before["version"]


def test_finance_handoff_duplicate_permission_and_atomic_reversal(stock):
    f = stock
    s = f["service"]
    move = f["complete"](f["movement"]())
    read_only = FinanceService(
        f["finance"].store, s.actor_uid, {"finance.read"}, FinanceDependencies(f["base"])
    )
    limited = Service(
        s.store,
        s.actor_uid,
        s.capabilities,
        Dependencies(f["base"], f["catalog"], finance_factory=lambda: OwnerPort(read_only)),
    )
    error(403, lambda: limited.post_finance(move["uid"], move["version"]))
    assert not s.get("movements", move["uid"])["finance_posted"]
    posted = s.post_finance(move["uid"], move["version"])
    entries = s.finance_entries(move["uid"])["items"]
    assert sum(Decimal(e["amount"]) for e in entries) == 0
    assert len(entries) == 2
    error(409, lambda: s.post_finance(move["uid"], posted["version"]))
    uid = uuid4()
    f["moves"].append(uid)
    payload = {
        "request_uid": uid,
        "expected_version": posted["version"],
        "reason": "Reverse receipt and valuation",
    }
    error(403, lambda: limited.reverse(move["uid"], payload))
    assert s.get("movements", move["uid"])["reversal_uid"] is None
    returned = s.reverse(move["uid"], payload)
    assert returned["finance_posted"]
    assert total(s, f["stock"]["uid"], f["locations"]["a"])["on_hand_ticks"] == 0
    original = {e["account_role"]: Decimal(e["amount"]) for e in entries}
    reverse = {
        e["account_role"]: Decimal(e["amount"]) for e in s.finance_entries(returned["uid"])["items"]
    }
    assert all(original[role] + reverse[role] == 0 for role in original)
    unposted = f["complete"](f["movement"](quantity="1"))
    rid = uuid4()
    f["moves"].append(rid)
    s.reverse(
        unposted["uid"],
        {
            "request_uid": rid,
            "expected_version": unposted["version"],
            "reason": "No valuation needed",
        },
    )
    error(
        409, lambda: s.post_finance(unposted["uid"], s.get("movements", unposted["uid"])["version"])
    )


def test_sales_full_line_claim_and_disabled_optional_modules(stock):
    schemas = Path(__file__).parent / "contracts/sdk-0.5.19/schemas"
    documents = [json.loads(p.read_text()) for p in schemas.glob("*.json")]
    registry = Registry().with_resources([(d["$id"], Resource.from_contents(d)) for d in documents])
    f = stock
    s = f["service"]
    f["complete"](f["movement"]())
    order = f["new"]()
    order = f["sales"].transition(order["uid"], "confirm", order["version"])
    uid = uuid4()
    f["moves"].append(uid)
    payload = {
        "request_uid": uid,
        "order_uid": order["uid"],
        "line_uid": order["lines"][0]["uid"],
        "expected_order_version": order["version"],
        "name": "Sales fulfillment",
        "stock_item_uid": f["stock"]["uid"],
        "source_uid": f["locations"]["a"]["uid"],
        "destination_uid": f["locations"]["customer"]["uid"],
    }
    claim = s.from_sales(payload)
    assert claim["quantity"] == "3"
    assert "inventory:" + str(uid) in f["sales"].get(order["uid"])["downstream"]
    second = uuid4()
    f["moves"].append(second)
    error(
        409,
        lambda: s.from_sales(
            {
                **payload,
                "request_uid": second,
                "expected_order_version": f["sales"].get(order["uid"])["version"],
            }
        ),
    )
    f["complete"](claim)
    standalone = Service(
        s.store, s.actor_uid, s.capabilities, Dependencies(f["base"], f["catalog"])
    )
    error(503, lambda: standalone.from_sales(payload))
    assert standalone.get("movements", claim["uid"])["state"] == "done"
    error(
        503,
        lambda: standalone.post_finance(claim["uid"], s.get("movements", claim["uid"])["version"]),
    )
    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 50000)
    ) as client:
        for resource in ["locations", "stock-items", "balances", "movements"]:
            response = client.get("/api/inventory/v1/" + resource + "/discovery/")
            assert response.status_code == 200, response.text
            schema = json.loads(
                (
                    Path(__file__).parent
                    / "contracts/sdk-0.5.19/schemas/resource-discovery-v1.schema.json"
                ).read_text()
            )
            Draft202012Validator(schema, registry=registry).validate(response.json())
            collection = client.get("/api/inventory/v1/" + resource + "/")
            assert collection.status_code == 200, collection.text
            schema = json.loads(
                (
                    Path(__file__).parent
                    / "contracts/sdk-0.5.19/schemas/resource-collection-v1.schema.json"
                ).read_text()
            )
            Draft202012Validator(schema, registry=registry).validate(collection.json())
        assert (
            client.get("/api/inventory/v1/ready/", headers={"x-user-uid": str(uuid4())}).status_code
            == 401
        )
        assert (
            client.get(
                "/api/inventory/v1/ready/", headers={"Origin": "https://evil.example"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/inventory/v1/movements/" + claim["uid"] + "/complete/",
                json={"expected_version": True},
            ).status_code
            == 422
        )


def test_archive_restore_precision_restart_and_isolation(stock, monkeypatch):
    f = stock
    s = f["service"]
    unused = f["location"]()
    archived = s.archive("locations", unused["uid"], unused["version"])
    restored = s.archive("locations", unused["uid"], archived["version"], restore=True)
    assert restored["archived_at"] is None
    move = f["movement"](quantity="0.01")
    done = f["complete"](move)
    assert done["net_value"] == "0.02"
    script = (
        "from metatables import configure_local_client;configure_local_client();from src.erp.inventory.store import Store;from src.erp.inventory.service import Service;from uuid import UUID;s=Service(Store(local_only=True),UUID('"
        + str(s.actor_uid)
        + "'),{'inventory.read'},None);assert s.get('movements','"
        + done["uid"]
        + "')['state']=='done';print('fresh stock persisted')"
    )
    result = subprocess.run(
        [".venv/bin/python", "-c", script], text=True, capture_output=True, check=True
    )
    assert "fresh stock persisted" in result.stdout
    assert upgrade_application("src.erp.inventory.migrations:migration")["revision"] == "0002"
    monkeypatch.setenv("INVENTORY_LOCAL_SOURCE_UID", str(uuid4()))
    with pytest.raises(RuntimeError):
        create_app()
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-c",
            "import sys;from api.erp.inventory.main import create_app;app=create_app(enabled=False);assert not any(getattr(r,'path','').startswith('/api/inventory') for r in app.routes);assert not any(k.startswith(('src.erp.sales','src.erp.finance','src.erp.crm')) for k in sys.modules);print('independent import')",
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    assert "independent import" in result.stdout


def test_policies_company_rules_and_zero_valuation(stock):
    f = stock
    s = f["service"]
    reader = Service(s.store, s.actor_uid, {"inventory.read"}, s.dependencies)
    error(
        403,
        lambda: reader.location(
            {
                "request_uid": uuid4(),
                "name": "Denied",
                "code": "DENIED",
                "usage": "internal",
                "operating_company_uid": f["payload"]["operating_company_uid"],
            }
        ),
    )
    error(409, lambda: f["policy"]())
    from sqlalchemy import delete

    from src.erp.base.metatables import AuditEvent as BaseAudit
    from src.erp.base.metatables import OperatingCompany
    from src.erp.catalog.metatables import AuditEvent as CatalogAudit
    from src.erp.catalog.metatables import Item
    from src.erp.catalog.schemas import ItemInput

    item = f["catalog"].save(
        "items",
        {
            **{k: f["item"][k] for k in ItemInput.model_fields},
            "code": "SERVICE-" + uuid4().hex[:10].upper(),
            "kind": "service",
        },
    )
    try:
        error(422, lambda: f["policy"](item_uid=item["uid"]))
    finally:
        f["catalog"].store.write(
            [
                delete(CatalogAudit).where(CatalogAudit.record_uid == UUID(item["uid"])),
                delete(Item).where(Item.uid == UUID(item["uid"])),
            ]
        )
    company = f["base"].save(
        "operating-companies",
        {
            "name": "Other stock company " + uuid4().hex[:8],
            "party_uid": f["payload"]["customer_uid"],
            "currency_uid": f["currency"]["uid"],
        },
    )
    try:
        location = f["location"](operating_company_uid=company["uid"])
        error(422, lambda: f["movement"](destination_uid=location["uid"]))
        zero = f["policy"](operating_company_uid=company["uid"], unit_cost="0")
        supplier = f["location"]("supplier", operating_company_uid=company["uid"])
        move = f["complete"](
            f["movement"](
                stock_item_uid=zero["uid"],
                source_uid=supplier["uid"],
                destination_uid=location["uid"],
                quantity="1",
            )
        )
        posted = s.post_finance(move["uid"], move["version"])
        assert posted["finance_posted"]
        entries = s.finance_entries(move["uid"])["items"]
        assert len(entries) == 2
        assert all(Decimal(e["amount"]) == 0 for e in entries)
        from api.erp.finance.local import create_app as finance_app

        with TestClient(
            finance_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 50000)
        ) as client:
            response = client.get("/api/finance/v1/inventory-valuations/" + move["uid"] + "/")
            assert response.status_code == 200, response.text
            assert len(response.json()["items"]) == 2
    finally:
        f["base"].store.write(
            [
                delete(BaseAudit).where(BaseAudit.record_uid == UUID(company["uid"])),
                delete(OperatingCompany).where(OperatingCompany.uid == UUID(company["uid"])),
            ]
        )
