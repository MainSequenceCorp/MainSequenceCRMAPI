from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from src.erp.inventory.errors import InventoryError
from src.erp.inventory.metatables import Entry
from src.erp.manufacturing.errors import ManufacturingError


def error(code, call):
    with pytest.raises(ManufacturingError) as e:
        call()
    assert e.value.status == code, e.value.message


def test_full_batch_steps_reconciliation_and_finance(manufacturing):
    f = manufacturing
    s = f["manufacturing"]
    inv = f["service"]
    f["seed"]()
    row = f["batch"]()
    error(409, lambda: s.transition(row["uid"], "complete", row["version"]))
    row = s.transition(row["uid"], "reserve", row["version"])
    assert inv.balance(f["stock"]["uid"], f["locations"]["a"]["uid"])["reserved_ticks"] == 400
    assert len(row["movement_uids"]) == 2
    error(
        409,
        lambda: s.step(
            row["uid"],
            row["steps"][1]["uid"],
            "start",
            {"expected_version": row["version"], "expected_step_version": 1},
        ),
    )
    for uid in row["movement_uids"]:
        move = inv.get("movements", uid)
        with pytest.raises(InventoryError):
            inv.transition(uid, "complete", move["version"])
    row = f["work"](row)
    row = s.transition(row["uid"], "complete", row["version"])
    assert inv.balance(f["stock"]["uid"], f["locations"]["a"]["uid"])["on_hand_ticks"] == 1600
    assert inv.balance(f["stock"]["uid"], f["locations"]["a"]["uid"])["reserved_ticks"] == 0
    assert (
        inv.balance(f["output_policy"]["uid"], f["locations"]["b"]["uid"])["on_hand_ticks"] == 200
    )
    row = s.transition(row["uid"], "finance", row["version"])
    valuation = s.valuation(row["uid"])
    assert len(valuation["items"]) == 2
    assert sum(Decimal(x["net_value"]) for x in valuation["items"]) == 0
    for item in valuation["items"]:
        assert item["finance_posted"] and len(item["entries"]) == 2
        assert sum(Decimal(x["amount"]) for x in item["entries"]) == 0
        with pytest.raises(InventoryError):
            inv.reverse(
                item["movement_uid"],
                {
                    "request_uid": uuid4(),
                    "expected_version": inv.get("movements", item["movement_uid"])["version"],
                    "reason": "Denied partial disassembly",
                },
            )
    error(409, lambda: s.transition(row["uid"], "finance", row["version"]))
    for policy, loc in [
        (f["stock"], f["locations"]["a"]),
        (f["output_policy"], f["locations"]["b"]),
    ]:
        entries = inv.store.read(
            select(Entry.quantity_ticks).where(
                Entry.stock_item_uid == UUID(policy["uid"]), Entry.location_uid == UUID(loc["uid"])
            )
        )
        assert (
            sum(x["quantity_ticks"] for x in entries)
            == inv.balance(policy["uid"], loc["uid"])["on_hand_ticks"]
        )


def test_maximum_batch_within_atomic_budget(manufacturing, monkeypatch):
    f = manufacturing
    s = f["manufacturing"]
    components = [{"item_uid": f["item"]["uid"], "quantity": "1"}]
    f["seed"]()
    for _ in range(7):
        item, policy = f["product"]("1.25")
        f["seed"](policy)
        components.append({"item_uid": item["uid"], "quantity": "1"})
    row = f["batch"](f["recipe"](components=components, operations=["Assemble"]))
    counts = []
    write = s.store.write

    def record(steps):
        counts.append(len(steps))
        return write(steps)

    monkeypatch.setattr(s.store, "write", record)
    row = s.transition(row["uid"], "reserve", row["version"])
    row = f["work"](row)
    row = s.transition(row["uid"], "complete", row["version"])
    row = s.transition(row["uid"], "finance", row["version"])
    assert len(row["movement_uids"]) == 9 and max(counts) <= 32
    assert len(s.valuation(row["uid"])["items"]) == 9


def test_reservation_race_cancel_and_late_rollback(manufacturing, monkeypatch):
    f = manufacturing
    s = f["manufacturing"]
    inv = f["service"]
    f["seed"](quantity="4")
    bom = f["recipe"]()
    rows = [f["batch"](bom), f["batch"](bom)]
    barrier = Barrier(2)

    def reserve(row):
        barrier.wait()
        try:
            return s.transition(row["uid"], "reserve", row["version"])
        except ManufacturingError as e:
            return e.status

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(reserve, rows))
    assert sum(isinstance(x, dict) for x in results) == 1 and 409 in results
    winner = next(x for x in results if isinstance(x, dict))
    s.transition(winner["uid"], "cancel", winner["version"])
    assert inv.balance(f["stock"]["uid"], f["locations"]["a"]["uid"])["reserved_ticks"] == 0
    draft = f["batch"](bom)
    original = inv.plan_prepare_production

    def stale(payload):
        uids, plan = original(payload)
        s.transition(draft["uid"], "cancel", draft["version"])
        return uids, plan

    monkeypatch.setattr(inv, "plan_prepare_production", stale)
    error(409, lambda: s.transition(draft["uid"], "reserve", draft["version"]))
    assert (
        s.get("orders", draft["uid"])["movement_uids"] == []
        and inv.balance(f["stock"]["uid"], f["locations"]["a"]["uid"])["reserved_ticks"] == 0
    )


def test_recipe_lifecycle_scaling_and_strict_versions(manufacturing):
    from pydantic import ValidationError

    from src.erp.manufacturing.schemas import BomInput, StepFinish

    f = manufacturing
    s = f["manufacturing"]
    error(422, lambda: f["recipe"](components=[{"item_uid": f["output"]["uid"], "quantity": "1"}]))
    error(422, lambda: f["recipe"](quantity="0.001"))
    recipe = f["recipe"](activate=False, quantity="3")
    payload = {k: recipe[k] for k in BomInput.model_fields if k != "components"}
    payload["components"] = [{"item_uid": f["item"]["uid"], "quantity": "1"}]
    recipe = s.bom(payload, uid=recipe["uid"], expected_version=recipe["version"])
    error(409, lambda: s.bom_action(recipe["uid"], "activate", 1))
    recipe = s.bom_action(recipe["uid"], "activate", recipe["version"])
    error(409, lambda: s.bom(payload, uid=recipe["uid"], expected_version=recipe["version"]))
    error(422, lambda: f["batch"](recipe, quantity="1"))
    row = f["batch"](recipe, quantity="3")
    s.bom_action(recipe["uid"], "archive", recipe["version"])
    error(409, lambda: s.transition(row["uid"], "reserve", row["version"]))
    error(409, lambda: f["batch"](recipe))
    with pytest.raises(ValidationError):
        StepFinish(expected_version=True, expected_step_version=1, minutes=2, evidence="x")
    with pytest.raises(ValidationError):
        StepFinish(expected_version=1, expected_step_version=1, minutes=2.5, evidence="x")


def test_owner_permissions_disabled_finance_and_source(manufacturing, monkeypatch):
    import src.erp.manufacturing.store as store_module
    from src.erp.finance.service import Service as FinanceService
    from src.erp.inventory.integrations import OwnerPort
    from src.erp.inventory.service import Service as InventoryService
    from src.erp.manufacturing.dependencies import InventoryPort
    from src.erp.manufacturing.service import Service

    f = manufacturing
    s = f["manufacturing"]
    inv = f["service"]
    f["seed"]()
    row = f["batch"]()
    denied = Service(s.store, s.actor_uid, {"manufacturing.read"}, s.dependencies)
    error(403, lambda: denied.transition(row["uid"], "reserve", row["version"]))
    denied_inventory = InventoryService(
        inv.store, inv.actor_uid, {"inventory.read"}, inv.dependencies
    )
    monkeypatch.setattr(s.dependencies, "inventory", InventoryPort(denied_inventory))
    error(403, lambda: s.transition(row["uid"], "reserve", row["version"]))
    monkeypatch.setattr(s.dependencies, "inventory", InventoryPort(inv))
    row = s.transition(row["uid"], "reserve", row["version"])
    row = f["work"](row)
    error(409, lambda: s.transition(row["uid"], "cancel", row["version"]))
    row = s.transition(row["uid"], "complete", row["version"])
    fin = f["finance"]
    denied_fin = FinanceService(fin.store, fin.actor_uid, {"finance.read"}, fin.dependencies)
    monkeypatch.setattr(inv.dependencies, "finance_factory", lambda: OwnerPort(denied_fin))
    error(403, lambda: s.transition(row["uid"], "finance", row["version"]))
    monkeypatch.setattr(inv.dependencies, "finance_factory", None)
    error(503, lambda: s.transition(row["uid"], "finance", row["version"]))
    assert not any(x["finance_posted"] for x in s.valuation(row["uid"])["items"])
    fake = type("Other", (), {"store": type("Store", (), {"data_source_uid": str(uuid4())})()})()
    monkeypatch.setattr(s.dependencies, "inventory", fake)
    error(503, s.inventory)
    monkeypatch.setattr(s.dependencies, "inventory", InventoryPort(inv))
    with monkeypatch.context() as patch:
        patch.setattr(store_module, "require_local_runtime", lambda: str(uuid4()))
        with pytest.raises(RuntimeError):
            s.store.write([])


def test_late_completion_guard_rolls_back_every_owner(manufacturing, monkeypatch):
    from sqlalchemy import update

    from metatables.compiled_sql.v1 import GuardedStatement
    from src.erp.inventory.metatables import Move

    f = manufacturing
    s = f["manufacturing"]
    inv = f["service"]
    f["seed"]()
    row = f["batch"]()
    row = s.transition(row["uid"], "reserve", row["version"])
    row = f["work"](row)
    original = inv.plan_transition_production

    def failing(*args):
        plan = original(*args)
        return [
            *plan,
            GuardedStatement(
                update(Move).where(Move.uid == uuid4()).values(version=2).returning(Move.uid),
                expect_rows=1,
                label="injected_late_conflict",
            ),
        ]

    with monkeypatch.context() as patch:
        patch.setattr(inv, "plan_transition_production", failing)
        error(409, lambda: s.transition(row["uid"], "complete", row["version"]))
    assert s.get("orders", row["uid"])["state"] == "progress"
    assert inv.balance(f["stock"]["uid"], f["locations"]["a"]["uid"])["reserved_ticks"] == 400
    assert inv.balance(f["output_policy"]["uid"], f["locations"]["b"]["uid"])["on_hand_ticks"] == 0
    row = s.transition(row["uid"], "complete", row["version"])
    original_finance = inv.plan_finance_production

    def failing_finance(*args):
        return [
            *original_finance(*args),
            GuardedStatement(
                update(Move).where(Move.uid == uuid4()).values(version=2).returning(Move.uid),
                expect_rows=1,
                label="injected_late_conflict",
            ),
        ]

    with monkeypatch.context() as patch:
        patch.setattr(inv, "plan_finance_production", failing_finance)
        error(409, lambda: s.transition(row["uid"], "finance", row["version"]))
    assert not s.get("orders", row["uid"])["finance_posted"]
    for uid in row["movement_uids"]:
        assert inv.finance_entries(uid)["items"] == []
        assert not inv.get("movements", uid)["finance_posted"]


def test_actual_http_contracts_persistence_and_independent_provider(manufacturing):
    import json
    import subprocess
    from pathlib import Path

    from fastapi.testclient import TestClient
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    from api.erp.manufacturing.local import create_app
    from metatables import upgrade_application
    from src.erp.manufacturing.metatables import MODELS

    f = manufacturing
    recipe = f["recipe"]()
    assert upgrade_application("src.erp.manufacturing.migrations:migration")["revision"] == "0001"
    assert {m.__metatable_namespace__ for m in MODELS} == {"erp-manufacturing"}
    code = """import sys
from metatables import configure_local_client
configure_local_client()
from src.erp.manufacturing.store import Store
from src.erp.manufacturing.metatables import Bom
from api.erp.manufacturing.main import create_app
from sqlalchemy import select
from uuid import UUID
assert 'src.erp.finance.service' not in sys.modules
assert not any(r.path.startswith('/api/manufacturing') for r in create_app(enabled=False).routes)
print(Store(local_only=True).read(select(Bom.uid).where(Bom.uid==UUID(sys.argv[1])))[0]['uid'])
"""
    assert recipe["uid"] in subprocess.check_output(
        [".venv/bin/python", "-c", code, recipe["uid"]], text=True
    )
    schemas = [
        json.loads(p.read_text())
        for p in Path("tests/erp/manufacturing/contracts/sdk-0.5.19/schemas").glob("*.json")
    ]
    registry = Registry().with_resources([(x["$id"], Resource.from_contents(x)) for x in schemas])
    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 50000)
    ) as client:
        ready = client.get("/api/manufacturing/v1/ready/")
        assert ready.status_code == 200, ready.text
        assert ready.json()["local"] is True
        for resource in ["boms", "orders"]:
            for suffix, name in [("", "resource-collection"), ("discovery/", "resource-discovery")]:
                response = client.get(f"/api/manufacturing/v1/{resource}/{suffix}")
                assert response.status_code == 200, response.text
                Draft202012Validator(
                    next(x for x in schemas if name in x["$id"]), registry=registry
                ).validate(response.json())
        for headers in [
            {"x-user-uid": str(uuid4())},
            {"Origin": "https://external.example"},
            {"Host": "external.example"},
        ]:
            assert client.get("/api/manufacturing/v1/ready/", headers=headers).status_code in (
                401,
                403,
            )
        assert client.get("/api/manufacturing/v1/orders/?ordering=created_at").status_code == 422
        assert (
            client.post(
                f"/api/manufacturing/v1/boms/{recipe['uid']}/archive/",
                json={"expected_version": True},
            ).status_code
            == 422
        )
