"""Owned actual local manufacturing fixtures with explicit cleanup of every owner."""

import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete

from metatables import upgrade_application
from src.erp.catalog.metatables import AuditEvent as CatalogAudit
from src.erp.catalog.metatables import Item
from src.erp.catalog.schemas import ItemInput
from src.erp.finance.metatables import AuditEvent as FinanceAudit
from src.erp.finance.metatables import Posting
from src.erp.inventory.metatables import AuditEvent as InventoryAudit
from src.erp.inventory.metatables import Balance, Entry, Move, StockItem
from src.erp.manufacturing.dependencies import Dependencies, InventoryPort
from src.erp.manufacturing.metatables import AuditEvent, Bom, BomLine, Production, WorkStep
from src.erp.manufacturing.service import Service
from src.erp.manufacturing.store import Store, require_local_runtime
from tests.erp.inventory.conftest import inventory_services, stock  # noqa: F401


@pytest.fixture
def manufacturing(stock):  # noqa: F811
    f = stock
    assert os.environ.get("MANUFACTURING_LOCAL_SOURCE_UID") == str(require_local_runtime())
    upgrade_application("src.erp.manufacturing.migrations:migration")
    s = Service(
        Store(local_only=True),
        f["service"].actor_uid,
        {
            "manufacturing.read",
            "manufacturing.write",
            "manufacturing.manage",
            "manufacturing.configure",
        },
        Dependencies(f["base"], f["catalog"], InventoryPort(f["service"])),
    )
    recipes, orders, products, policies = [], [], [], []

    def product(cost="5.00"):
        item = f["catalog"].save(
            "items",
            {
                **{k: f["item"][k] for k in ItemInput.model_fields},
                "name": "Manufacturing product " + uuid4().hex[:8],
                "code": "MFG-" + uuid4().hex[:12].upper(),
            },
        )
        products.append(UUID(item["uid"]))
        policy = f["policy"](item_uid=item["uid"], unit_cost=cost)
        policies.append(UUID(policy["uid"]))
        return item, policy

    try:
        output, output_policy = product()
        production_location = f["location"]("production")

        def recipe(components=None, operations=None, activate=True, **changes):
            uid = uuid4()
            recipes.append(uid)
            row = s.bom(
                {
                    "name": "BOM-" + uuid4().hex[:12].upper(),
                    "item_uid": output["uid"],
                    "quantity": "1",
                    "components": components or [{"item_uid": f["item"]["uid"], "quantity": "2"}],
                    "operations": operations or ["Assemble", "Inspect"],
                    **changes,
                },
                request_uid=uid,
            )
            return s.bom_action(uid, "activate", row["version"]) if activate else row

        def batch(bom=None, **changes):
            bom = bom or recipe()
            uid = uuid4()
            orders.append(uid)
            return s.production(
                {
                    "request_uid": uid,
                    "name": "MO-" + uuid4().hex[:12].upper(),
                    "bom_uid": bom["uid"],
                    "expected_bom_version": bom["version"],
                    "quantity": "2",
                    "operating_company_uid": f["payload"]["operating_company_uid"],
                    "source_uid": f["locations"]["a"]["uid"],
                    "destination_uid": f["locations"]["b"]["uid"],
                    "production_location_uid": production_location["uid"],
                    **changes,
                }
            )

        def seed(policy=None, quantity="20"):
            return f["complete"](
                f["movement"](stock_item_uid=(policy or f["stock"])["uid"], quantity=quantity)
            )

        def work(row):
            for original in row["steps"]:
                row = s.step(
                    row["uid"],
                    original["uid"],
                    "start",
                    {
                        "expected_version": row["version"],
                        "expected_step_version": original["version"],
                    },
                )
                step = next(x for x in row["steps"] if x["uid"] == original["uid"])
                row = s.step(
                    row["uid"],
                    step["uid"],
                    "finish",
                    {
                        "expected_version": row["version"],
                        "expected_step_version": step["version"],
                        "minutes": 5,
                        "evidence": "Owned work check",
                    },
                )
            return row

        yield {
            **f,
            "manufacturing": s,
            "recipe": recipe,
            "batch": batch,
            "product": product,
            "seed": seed,
            "work": work,
            "output": output,
            "output_policy": output_policy,
            "production_location": production_location,
            "manufacturing_orders": orders,
            "manufacturing_recipes": recipes,
        }
    finally:
        for uid in orders:
            try:
                row = s.get("orders", uid)
            except Exception as e:
                if getattr(e, "status", None) == 404:
                    continue
                raise
            # Release held fixture reservations before deleting trace records.
            if row["state"] in {"draft", "ready"}:
                row = s.transition(uid, "cancel", row["version"])
            elif row["state"] == "progress":
                f["service"].transact(
                    f["service"].plan_transition_production(uid, row["movement_uids"], "cancel")
                )
            for move_uid in row["movement_uids"]:
                mid = UUID(move_uid)
                f["finance"].store.write(
                    [
                        delete(Posting).where(
                            Posting.resource == "inventory", Posting.record_uid == mid
                        ),
                        delete(FinanceAudit).where(
                            FinanceAudit.resource == "inventory", FinanceAudit.record_uid == mid
                        ),
                    ]
                )
                f["service"].store.write(
                    [
                        delete(Entry).where(Entry.move_uid == mid),
                        delete(InventoryAudit).where(InventoryAudit.record_uid == mid),
                        delete(Move).where(Move.uid == mid),
                    ]
                )
            s.store.write(
                [
                    delete(WorkStep).where(WorkStep.production_uid == uid),
                    delete(AuditEvent).where(AuditEvent.record_uid == uid),
                    delete(Production).where(Production.uid == uid),
                ]
            )
        for uid in recipes:
            s.store.write(
                [
                    delete(BomLine).where(BomLine.bom_uid == uid),
                    delete(AuditEvent).where(AuditEvent.record_uid == uid),
                    delete(Bom).where(Bom.uid == uid),
                ]
            )
        # Remove seed movements for extra products before their stock policies.
        for move_uid in f["moves"]:
            f["service"].store.write(
                [
                    delete(Entry).where(Entry.move_uid == move_uid),
                    delete(InventoryAudit).where(InventoryAudit.record_uid == move_uid),
                    delete(Move).where(Move.uid == move_uid),
                ]
            )
        for uid in policies:
            f["service"].store.write(
                [
                    delete(Balance).where(Balance.stock_item_uid == uid),
                    delete(InventoryAudit).where(InventoryAudit.record_uid == uid),
                    delete(StockItem).where(StockItem.uid == uid),
                ]
            )
        for uid in products:
            f["catalog"].store.write(
                [
                    delete(CatalogAudit).where(CatalogAudit.record_uid == uid),
                    delete(Item).where(Item.uid == uid),
                ]
            )
