import os
from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, or_

from mainsequence.client import User
from metatables import configure_local_client, upgrade_application
from src.erp.base.metatables import RESOURCES as BASE
from src.erp.base.metatables import AuditEvent as BaseAudit
from src.erp.base.service import Service as BaseService
from src.erp.base.store import Store as BaseStore
from src.erp.finance.dependencies import Dependencies
from src.erp.finance.metatables import RESOURCES, Allocation, AuditEvent, InvoiceLine, Posting
from src.erp.finance.service import Service
from src.erp.finance.store import Store, require_local_runtime


@pytest.fixture(scope="session")
def finance_services():
    configure_local_client()
    expected = os.environ.get("FINANCE_LOCAL_SOURCE_UID")
    assert expected and str(require_local_runtime()) == expected
    upgrade_application("src.erp.finance.migrations:migration")
    actor = User.get_authenticated_user_details().uid
    base = BaseService(
        BaseStore(local_only=True), actor, {"base.read", "base.write", "base.configure"}
    )
    service = Service(
        Store(local_only=True),
        actor,
        {"finance.read", "finance.write", "finance.post", "finance.configure"},
        Dependencies(base),
    )
    return service, base


@pytest.fixture
def business(finance_services):
    svc, base = finance_services
    owned = []
    documents = []

    def create(resource, **values):
        row = base.save(resource, {"name": "Finance fixture " + uuid4().hex[:8], **values})
        owned.append((resource, UUID(row["uid"])))
        return row

    currency = base.collection("currencies", search="EUR")["items"][0]
    party = create("parties", kind="organization")
    issuer = create("parties", kind="organization")
    company = create("operating-companies", party_uid=issuer["uid"], currency_uid=currency["uid"])
    payload = {
        "name": "F-" + uuid4().hex[:12].upper(),
        "kind": "customer",
        "party_uid": party["uid"],
        "operating_company_uid": company["uid"],
        "currency_uid": currency["uid"],
        "document_date": date.today(),
    }

    def new(resource="invoices", **changes):
        uid = uuid4()
        documents.append((resource, uid))
        data = {**payload, "name": "F-" + uuid4().hex[:12].upper()}
        if resource == "invoices":
            data.update(
                due_date=date.today(),
                lines=[
                    {
                        "description": "Consulting",
                        "quantity": "2",
                        "unit_price": "50",
                        "tax_rate": "20",
                    }
                ],
            )
        else:
            data.update(amount="120", external_reference="Observed local fixture")
        return svc.save(resource, {**data, **changes}, request_uid=uid)

    yield {
        "service": svc,
        "base": base,
        "new": new,
        "payload": payload,
        "documents": documents,
        "currency": currency,
        "party": party,
        "company": company,
    }
    ids = [uid for _, uid in documents]
    if ids:
        svc.store.write(
            [
                delete(Allocation).where(
                    or_(Allocation.invoice_uid.in_(ids), Allocation.payment_uid.in_(ids))
                )
            ]
        )
    for resource, uid in reversed(documents):
        steps = [
            delete(Posting).where(Posting.resource == resource, Posting.record_uid == uid),
            delete(AuditEvent).where(AuditEvent.resource == resource, AuditEvent.record_uid == uid),
        ]
        if resource == "invoices":
            steps.append(delete(InvoiceLine).where(InvoiceLine.invoice_uid == uid))
        steps.append(delete(RESOURCES[resource]).where(RESOURCES[resource].uid == uid))
        svc.store.write(steps)
    for resource, uid in reversed(owned):
        base.store.write(
            [
                delete(BaseAudit).where(BaseAudit.record_uid == uid),
                delete(BASE[resource]).where(BASE[resource].uid == uid),
            ]
        )
