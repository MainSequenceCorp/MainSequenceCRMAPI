import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete

from mainsequence.client import User
from metatables import configure_local_client, upgrade_application
from src.erp.base.metatables import RESOURCES as BASE
from src.erp.base.metatables import AuditEvent as BaseAudit
from src.erp.base.service import Service as BaseService
from src.erp.base.store import Store as BaseStore
from src.erp.catalog.metatables import RESOURCES as CATALOG
from src.erp.catalog.metatables import AuditEvent as CatalogAudit
from src.erp.catalog.service import Service as CatalogService
from src.erp.catalog.store import Store as CatalogStore
from src.erp.sales.dependencies import Dependencies
from src.erp.sales.metatables import AuditEvent, Order, OrderLine
from src.erp.sales.service import Service
from src.erp.sales.store import Store, require_local_runtime


@pytest.fixture(scope="session")
def services():
    expected = os.environ.get("SALES_LOCAL_SOURCE_UID")
    if not expected:
        pytest.fail("Set SALES_LOCAL_SOURCE_UID to the verified local SQLite source")
    configure_local_client()
    assert str(require_local_runtime()) == expected
    upgrade_application("src.erp.sales.migrations:migration")
    actor = User.get_authenticated_user_details().uid
    base = BaseService(
        BaseStore(local_only=True), actor, {"base.read", "base.write", "base.configure"}
    )
    catalog = CatalogService(
        CatalogStore(local_only=True), actor, {"catalog.read", "catalog.write", "catalog.configure"}
    )
    sales = Service(
        Store(local_only=True),
        actor,
        {"sales.read", "sales.write", "sales.configure"},
        Dependencies(base, catalog, local=True),
    )
    return sales, base, catalog


@pytest.fixture
def business(services):
    sales, base, catalog = services
    owned = []
    orders = []

    def create(owner, resource, **data):
        service = base if owner == "base" else catalog
        row = service.save(
            resource,
            {
                "name": "Sales fixture " + uuid4().hex[:8],
                **({"code": "TEST-" + uuid4().hex[:12].upper()} if owner == "catalog" else {}),
                **data,
            },
        )
        owned.append((owner, resource, UUID(row["uid"])))
        return row

    currency = base.collection("currencies")["items"][0]
    customer = create("base", "parties", kind="organization")
    issuer = create("base", "parties", kind="organization")
    company = create(
        "base", "operating-companies", party_uid=issuer["uid"], currency_uid=currency["uid"]
    )
    group = create("catalog", "unit-groups")
    unit = create("catalog", "units", group_uid=group["uid"], is_reference=True)
    category = create("catalog", "categories")
    item = create(
        "catalog", "items", kind="service", unit_uid=unit["uid"], category_uid=category["uid"]
    )
    payload = {
        "name": "Q-" + uuid4().hex[:12].upper(),
        "customer_uid": customer["uid"],
        "operating_company_uid": company["uid"],
        "currency_uid": currency["uid"],
        "lines": [
            {"item_uid": item["uid"], "quantity": "3", "unit_price": "12.50", "discount": "10"}
        ],
    }

    def new(**changes):
        uid = uuid4()
        orders.append(uid)
        return sales.save(
            {**payload, "name": "Q-" + uuid4().hex[:12].upper(), **changes}, request_uid=uid
        )

    yield {
        "sales": sales,
        "base": base,
        "catalog": catalog,
        "payload": payload,
        "new": new,
        "orders": orders,
        "item": item,
        "currency": currency,
    }
    for uid in reversed(orders):
        sales.store.write(
            [
                delete(AuditEvent).where(AuditEvent.record_uid == uid),
                delete(OrderLine).where(OrderLine.order_uid == uid),
                delete(Order).where(Order.uid == uid),
            ]
        )
    for owner, key, uid in reversed(owned):
        service, models, audit = (
            (base, BASE, BaseAudit) if owner == "base" else (catalog, CATALOG, CatalogAudit)
        )
        service.store.write(
            [
                delete(audit).where(audit.record_uid == uid),
                delete(models[key]).where(models[key].uid == uid),
            ]
        )
