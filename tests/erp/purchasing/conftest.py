"""Verified Local SQLite fixtures, owner APIs and explicit UID cleanup."""

import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete

from metatables import upgrade_application
from src.erp.finance.metatables import AuditEvent as FinanceAudit
from src.erp.finance.metatables import Invoice, InvoiceLine
from src.erp.purchasing.dependencies import Dependencies
from src.erp.purchasing.integrations import OwnerPort
from src.erp.purchasing.metatables import AuditEvent, Order, OrderLine, Receipt
from src.erp.purchasing.service import Service
from src.erp.purchasing.store import Store, require_local_runtime
from tests.erp.inventory.conftest import inventory_services, stock  # noqa: F401


@pytest.fixture
def purchase(stock):  # noqa: F811
    f = stock
    assert os.environ.get("PURCHASING_LOCAL_SOURCE_UID") == str(require_local_runtime())
    upgrade_application("src.erp.purchasing.migrations:migration")
    svc = Service(
        Store(local_only=True),
        f["service"].actor_uid,
        {"purchasing.read", "purchasing.write", "purchasing.manage", "purchasing.configure"},
        Dependencies(
            f["base"],
            f["catalog"],
            lambda: OwnerPort(f["service"]),
            lambda: OwnerPort(f["finance"]),
        ),
    )
    payload = {
        "supplier_uid": f["payload"]["customer_uid"],
        "operating_company_uid": f["payload"]["operating_company_uid"],
        "currency_uid": f["payload"]["currency_uid"],
        "lines": f["payload"]["lines"],
    }
    from src.erp.catalog.metatables import AuditEvent as CatalogAudit
    from src.erp.catalog.metatables import Item, Unit
    from src.erp.catalog.schemas import ItemInput

    service_item = f["catalog"].save(
        "items",
        {
            **{k: f["item"][k] for k in ItemInput.model_fields},
            "code": "PS-" + uuid4().hex[:12].upper(),
            "kind": "service",
        },
    )
    extra_units = []
    extra_items = []
    orders, bills = [], []

    def new(**changes):
        uid = uuid4()
        orders.append(uid)
        return svc.save(
            {**payload, "name": "PO-" + uuid4().hex[:12].upper(), **changes}, request_uid=uid
        )

    def confirm(**changes):
        row = new(**changes)
        return svc.transition(row["uid"], "confirm", row["version"])

    def receipt(row):
        uid = uuid4()
        f["moves"].append(uid)
        return svc.receipt(
            row["uid"],
            row["lines"][0]["uid"],
            {
                "expected_version": row["version"],
                "request_uid": uid,
                "name": "PO-R-" + uuid4().hex[:8],
                "stock_item_uid": f["stock"]["uid"],
                "source_uid": f["locations"]["supplier"]["uid"],
                "destination_uid": f["locations"]["a"]["uid"],
            },
        )

    def bill(row, **changes):
        uid = uuid4()
        bills.append(uid)
        return svc.bill(
            row["uid"],
            {
                "expected_version": row["version"],
                "request_uid": uid,
                "name": "BILL-" + uuid4().hex[:8].upper(),
                "document_date": "2026-11-17",
                "due_date": "2026-12-17",
                **changes,
            },
        )

    yield {
        **f,
        "purchasing": svc,
        "new_purchase": new,
        "confirm_purchase": confirm,
        "receive_purchase": receipt,
        "bill_purchase": bill,
        "purchase_orders": orders,
        "purchase_bills": bills,
        "purchase_payload": payload,
        "service_item": service_item,
        "extra_units": extra_units,
        "extra_items": extra_items,
    }
    for uid in bills:
        f["finance"].store.write(
            [
                delete(InvoiceLine).where(InvoiceLine.invoice_uid == uid),
                delete(FinanceAudit).where(FinanceAudit.record_uid == uid),
                delete(Invoice).where(Invoice.uid == uid),
            ]
        )
    for uid in orders:
        svc.store.write(
            [
                delete(Receipt).where(Receipt.order_uid == uid),
                delete(OrderLine).where(OrderLine.order_uid == uid),
                delete(AuditEvent).where(AuditEvent.record_uid == uid),
                delete(Order).where(Order.uid == uid),
            ]
        )

    f["catalog"].store.write(
        [
            delete(CatalogAudit).where(CatalogAudit.record_uid == UUID(service_item["uid"])),
            delete(Item).where(Item.uid == UUID(service_item["uid"])),
        ]
    )
    for value in extra_items:
        uid = UUID(value)
        f["catalog"].store.write(
            [
                delete(CatalogAudit).where(CatalogAudit.record_uid == uid),
                delete(Item).where(Item.uid == uid),
            ]
        )
    for uid in extra_units:
        f["catalog"].store.write(
            [
                delete(CatalogAudit).where(CatalogAudit.record_uid == uid),
                delete(Unit).where(Unit.uid == uid),
            ]
        )
