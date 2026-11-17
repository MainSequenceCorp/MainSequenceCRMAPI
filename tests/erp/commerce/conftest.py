"""Owned actual local Commerce fixtures, exact-ID cleanup through every owner."""

import os
from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from tests.erp.sales.conftest import business, services  # noqa: F401

from metatables import upgrade_application
from src.erp.catalog.metatables import AuditEvent as CatalogAudit
from src.erp.catalog.metatables import Item
from src.erp.catalog.schemas import ItemInput
from src.erp.commerce.dependencies import Dependencies, OwnerPort
from src.erp.commerce.metatables import AuditEvent, Checkout, Offer, PortalGrant, Site
from src.erp.commerce.service import Service
from src.erp.commerce.store import Store, require_local_runtime
from src.erp.finance.dependencies import Dependencies as FinanceDependencies
from src.erp.finance.metatables import Allocation, Invoice, InvoiceLine, Payment, Posting
from src.erp.finance.metatables import AuditEvent as FinanceAudit
from src.erp.finance.service import Service as FinanceService
from src.erp.finance.store import Store as FinanceStore


@pytest.fixture
def commerce(business):  # noqa: F811
    f = business
    assert os.environ.get("COMMERCE_LOCAL_SOURCE_UID") == str(require_local_runtime())
    upgrade_application("src.erp.commerce.migrations:migration")
    sales, base, catalog = f["sales"], f["base"], f["catalog"]
    fin = FinanceService(
        FinanceStore(local_only=True),
        sales.actor_uid,
        {"finance.read", "finance.write", "finance.post", "finance.configure"},
        FinanceDependencies(base, lambda: OwnerPort(sales)),
    )
    s = Service(
        Store(local_only=True),
        sales.actor_uid,
        {"commerce.read", "commerce.write", "commerce.manage", "commerce.configure"},
        Dependencies(base, catalog, lambda: OwnerPort(sales), lambda: OwnerPort(fin)),
    )
    extra_items = []
    owned = {k: [] for k in ["sites", "offers", "grants", "checkouts", "invoices", "payments"]}

    def product(kind="service"):
        row = catalog.save(
            "items",
            {
                **{k: f["item"][k] for k in ItemInput.model_fields},
                "code": "WEB-" + uuid4().hex[:12].upper(),
                "name": "Commerce item " + uuid4().hex[:8],
                "kind": kind,
            },
        )
        extra_items.append(UUID(row["uid"]))
        return row

    def create_site(publish=True, **changes):
        uid = uuid4()
        owned["sites"].append(uid)
        row = s.save(
            "sites",
            {
                "name": "Website " + uid.hex[:8],
                "slug": "site-" + uid.hex[:12],
                "body": "Local service shop",
                "operating_company_uid": f["payload"]["operating_company_uid"],
                "currency_uid": f["currency"]["uid"],
                **changes,
            },
            request_uid=uid,
        )
        return s.publish("sites", uid, "publish", row["version"]) if publish else row

    def create_offer(site, publish=True, **changes):
        uid = uuid4()
        owned["offers"].append(uid)
        row = s.save(
            "offers",
            {
                "site_uid": site["uid"],
                "item_uid": f["item"]["uid"],
                "name": "Service " + uid.hex[:8],
                "description": "Service fixture",
                "unit_price": "12.50",
                **changes,
            },
            request_uid=uid,
        )
        return s.publish("offers", uid, "publish", row["version"]) if publish else row

    def grant(site, **changes):
        uid = uuid4()
        owned["grants"].append(uid)
        return s.issue_grant(
            {
                "request_uid": uid,
                "site_uid": site["uid"],
                "customer_uid": f["payload"]["customer_uid"],
                **changes,
            }
        )

    def checkout(token, site, offer, **changes):
        uid = uuid4()
        owned["checkouts"].append(uid)
        payload = {
            "request_uid": uid,
            "expected_site_version": site["version"],
            "lines": [
                {"offer_uid": offer["uid"], "expected_version": offer["version"], "quantity": "2"}
            ],
            **changes,
        }
        return s.checkout(token, payload), payload

    def invoice(row, **changes):
        uid = uuid4()
        owned["invoices"].append(uid)
        return s.invoice(
            row["uid"],
            {
                "request_uid": uid,
                "expected_version": row["version"],
                "name": "WEBINV-" + uid.hex[:12].upper(),
                "document_date": date.today(),
                "due_date": date.today(),
                **changes,
            },
        )

    def pay(row, **changes):
        invoice = fin.get("invoices", row["invoice_uid"])
        if invoice["state"] == "draft":
            invoice = fin.transition("invoices", invoice["uid"], "post", invoice["version"])
        uid = uuid4()
        owned["payments"].append(uid)
        payment = fin.save(
            "payments",
            {
                "name": "WEBPAY-" + uid.hex[:12].upper(),
                "kind": "customer",
                "party_uid": invoice["party_uid"],
                "operating_company_uid": invoice["operating_company_uid"],
                "currency_uid": invoice["currency_uid"],
                "document_date": date.today(),
                "amount": invoice["total"],
                "external_reference": "Observed disposable local receipt",
                **changes,
            },
            request_uid=uid,
        )
        payment = fin.transition("payments", payment["uid"], "post", payment["version"])
        allocation = fin.allocate(
            {
                "request_uid": uuid4(),
                "invoice_uid": invoice["uid"],
                "payment_uid": payment["uid"],
                "expected_invoice_version": invoice["version"],
                "expected_payment_version": payment["version"],
                "amount": payment["total"],
            }
        )
        return allocation

    try:
        site = create_site()
        offer = create_offer(site)
        access = grant(site)
        yield {
            **f,
            "commerce": s,
            "finance": fin,
            "site": site,
            "offer": offer,
            "access": access,
            "create_site": create_site,
            "create_offer": create_offer,
            "grant": grant,
            "checkout": checkout,
            "invoice": invoice,
            "pay": pay,
            "commerce_owned": owned,
            "product": product,
        }
    finally:
        # Include browser-created children by the exact site IDs this fixture owns.
        if owned["sites"]:
            for model, name in [
                (Checkout, "checkouts"),
                (Offer, "offers"),
                (PortalGrant, "grants"),
            ]:
                rows = s.store.read(
                    select(model.__table__).where(model.site_uid.in_(owned["sites"])).limit(100)
                )
                for row in rows:
                    uid = UUID(row["uid"])
                    if uid not in owned[name]:
                        owned[name].append(uid)
                    if name == "checkouts":
                        f["orders"].append(UUID(row["sales_order_uid"]))
                        if row["invoice_uid"] and UUID(row["invoice_uid"]) not in owned["invoices"]:
                            owned["invoices"].append(UUID(row["invoice_uid"]))
        for uid in owned["invoices"]:
            fin.store.write(
                [
                    delete(Allocation).where(Allocation.invoice_uid == uid),
                    delete(Posting).where(
                        Posting.resource == "invoices", Posting.record_uid == uid
                    ),
                    delete(FinanceAudit).where(
                        FinanceAudit.resource == "invoices", FinanceAudit.record_uid == uid
                    ),
                    delete(InvoiceLine).where(InvoiceLine.invoice_uid == uid),
                    delete(Invoice).where(Invoice.uid == uid),
                ]
            )
        for uid in owned["payments"]:
            fin.store.write(
                [
                    delete(Allocation).where(Allocation.payment_uid == uid),
                    delete(Posting).where(
                        Posting.resource == "payments", Posting.record_uid == uid
                    ),
                    delete(FinanceAudit).where(
                        FinanceAudit.resource == "payments", FinanceAudit.record_uid == uid
                    ),
                    delete(Payment).where(Payment.uid == uid),
                ]
            )
        for resource, model in [
            ("checkouts", Checkout),
            ("grants", PortalGrant),
            ("offers", Offer),
            ("sites", Site),
        ]:
            for uid in set(owned[resource]):
                s.store.write(
                    [
                        delete(AuditEvent).where(
                            AuditEvent.resource == resource, AuditEvent.record_uid == uid
                        ),
                        delete(model).where(model.uid == uid),
                    ]
                )

        for uid in extra_items:
            catalog.store.write(
                [
                    delete(CatalogAudit).where(CatalogAudit.record_uid == uid),
                    delete(Item).where(Item.uid == uid),
                ]
            )
