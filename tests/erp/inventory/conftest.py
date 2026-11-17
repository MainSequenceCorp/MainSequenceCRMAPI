"""Owned actual Local SQLite inventory fixtures; never direct database connections."""

import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete

from metatables import upgrade_application
from src.erp.catalog.schemas import ItemInput
from src.erp.finance.dependencies import Dependencies as FinanceDependencies
from src.erp.finance.metatables import AuditEvent as FinanceAudit
from src.erp.finance.metatables import Posting
from src.erp.finance.service import Service as FinanceService
from src.erp.finance.store import Store as FinanceStore
from src.erp.inventory.dependencies import Dependencies
from src.erp.inventory.integrations import OwnerPort
from src.erp.inventory.metatables import AuditEvent, Balance, Entry, Location, Move, StockItem
from src.erp.inventory.service import Service
from src.erp.inventory.store import Store, require_local_runtime
from tests.erp.sales.conftest import business as sales_business
from tests.erp.sales.conftest import services as sales_services


@pytest.fixture(scope="session")
def inventory_services():
    sales, base, catalog = sales_services.__wrapped__()
    expected = os.environ.get("INVENTORY_LOCAL_SOURCE_UID")
    assert expected and str(require_local_runtime()) == expected
    upgrade_application("src.erp.inventory.migrations:migration")
    finance = FinanceService(
        FinanceStore(local_only=True),
        sales.actor_uid,
        {"finance.read", "finance.write", "finance.post", "finance.configure"},
        FinanceDependencies(base),
    )
    service = Service(
        Store(local_only=True),
        sales.actor_uid,
        {"inventory.read", "inventory.write", "inventory.manage", "inventory.configure"},
        Dependencies(base, catalog, lambda: OwnerPort(sales), lambda: OwnerPort(finance)),
    )
    return service, sales, base, catalog, finance


@pytest.fixture
def stock(inventory_services):
    svc, sales, base, catalog, finance = inventory_services
    parent = sales_business.__wrapped__((sales, base, catalog))
    f = next(parent)
    item = f["item"]
    item = catalog.save(
        "items",
        {
            **{k: item[k] for k in ItemInput.model_fields},
            "code": "INV-" + uuid4().hex[:12].upper(),
            "kind": "product",
        },
    )
    f["payload"]["lines"][0]["item_uid"] = item["uid"]
    moves = []
    stocks = []
    locations = []

    def policy(**changes):
        uid = uuid4()
        stocks.append(uid)
        return svc.stock_item(
            {
                "request_uid": uid,
                "item_uid": item["uid"],
                "operating_company_uid": f["payload"]["operating_company_uid"],
                "unit_cost": "2.50",
                **changes,
            }
        )

    product = policy()

    def location(usage="internal", **changes):
        uid = uuid4()
        locations.append(uid)
        return svc.location(
            {
                "request_uid": uid,
                "name": usage + " " + uuid4().hex[:8],
                "code": "LOC-" + uuid4().hex[:12].upper(),
                "usage": usage,
                "operating_company_uid": f["payload"]["operating_company_uid"],
                **changes,
            }
        )

    locs = {
        name: location(usage)
        for name, usage in [
            ("supplier", "supplier"),
            ("a", "internal"),
            ("b", "internal"),
            ("customer", "customer"),
            ("adjustment", "adjustment"),
        ]
    }

    def movement(source="supplier", destination="a", quantity="10", **changes):
        uid = uuid4()
        moves.append(uid)
        return svc.movement(
            {
                "request_uid": uid,
                "name": "STOCK-" + uuid4().hex[:8],
                "stock_item_uid": product["uid"],
                "source_uid": locs[source]["uid"],
                "destination_uid": locs[destination]["uid"],
                "quantity": quantity,
                "reason": "Owned stock test",
                **changes,
            }
        )

    def complete(move):
        prepared = svc.transition(move["uid"], "prepare", move["version"])
        return svc.transition(prepared["uid"], "complete", prepared["version"])

    yield {
        **f,
        "item": item,
        "service": svc,
        "finance": finance,
        "stock": product,
        "policy": policy,
        "location": location,
        "locations": locs,
        "movement": movement,
        "complete": complete,
        "moves": moves,
        "stocks": stocks,
        "location_uids": locations,
    }
    try:
        for uid in moves:
            finance.store.write(
                [
                    delete(Posting).where(
                        Posting.resource == "inventory", Posting.record_uid == uid
                    ),
                    delete(FinanceAudit).where(
                        FinanceAudit.resource == "inventory", FinanceAudit.record_uid == uid
                    ),
                ]
            )
            svc.store.write(
                [
                    delete(Entry).where(Entry.move_uid == uid),
                    delete(AuditEvent).where(AuditEvent.record_uid == uid),
                    delete(Move).where(Move.uid == uid),
                ]
            )
        for uid in stocks:
            svc.store.write(
                [
                    delete(Balance).where(Balance.stock_item_uid == uid),
                    delete(AuditEvent).where(AuditEvent.record_uid == uid),
                    delete(StockItem).where(StockItem.uid == uid),
                ]
            )
        for uid in locations:
            svc.store.write(
                [
                    delete(AuditEvent).where(AuditEvent.record_uid == uid),
                    delete(Location).where(Location.uid == uid),
                ]
            )
    finally:
        from src.erp.catalog.metatables import AuditEvent as CatalogAudit
        from src.erp.catalog.metatables import Item

        try:
            catalog.store.write(
                [
                    delete(CatalogAudit).where(CatalogAudit.record_uid == UUID(item["uid"])),
                    delete(Item).where(Item.uid == UUID(item["uid"])),
                ]
            )
        finally:
            try:
                next(parent)
            except StopIteration:
                pass
