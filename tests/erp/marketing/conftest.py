import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select

from mainsequence.client import User
from metatables import configure_local_client, upgrade_application
from src.erp.base.metatables import RESOURCES as BASE
from src.erp.base.metatables import AuditEvent as BaseAudit
from src.erp.base.service import Service as BaseService
from src.erp.base.store import Store as BaseStore
from src.erp.marketing.dependencies import Dependencies
from src.erp.marketing.metatables import AuditEvent, DeliveryEvent, Mailing, Recipient, Subscriber
from src.erp.marketing.service import Service
from src.erp.marketing.store import Store, require_local_runtime


@pytest.fixture(scope="session")
def marketing_services():
    configure_local_client()
    expected = os.environ.get("MARKETING_LOCAL_SOURCE_UID")
    assert expected and str(require_local_runtime()) == expected
    upgrade_application("src.erp.marketing.migrations:migration")
    actor = User.get_authenticated_user_details().uid
    base = BaseService(
        BaseStore(local_only=True), actor, {"base.read", "base.write", "base.configure"}
    )
    return Service(
        Store(local_only=True),
        actor,
        {"marketing.read", "marketing.write", "marketing.manage"},
        Dependencies(base, local=True),
    ), base


@pytest.fixture
def mailings(marketing_services):
    svc, base = marketing_services
    people = []
    subscribers = []
    mailings = []

    def person(**changes):
        row = base.save(
            "parties",
            {
                "name": "Marketing person " + uuid4().hex[:10],
                "kind": "person",
                "emails": [uuid4().hex + "@example.com"],
                **changes,
            },
        )
        people.append(UUID(row["uid"]))
        return row

    def subscriber(party=None, **changes):
        party = party or person()
        uid = uuid4()
        subscribers.append(uid)
        return svc.subscriber(
            {
                "request_uid": uid,
                "party_uid": party["uid"],
                "email": party["emails"][0],
                "evidence": "Owned local subscription fixture",
                **changes,
            }
        )

    def mailing(**changes):
        uid = uuid4()
        mailings.append(uid)
        return svc.mailing(
            {
                "request_uid": uid,
                "name": "Mailing " + uuid4().hex[:10],
                "subject": "Local preview",
                "body": "Owned capture fixture",
                "sender_email": "preview@example.com",
                **changes,
            }
        )

    def add(row, sub):
        return svc.add_recipient(
            row["uid"],
            {
                "request_uid": uuid4(),
                "subscriber_uid": sub["uid"],
                "expected_version": row["version"],
            },
        )

    yield {
        "service": svc,
        "base": base,
        "person": person,
        "subscriber": subscriber,
        "mailing": mailing,
        "add": add,
        "people": people,
        "mailings": mailings,
        "subscribers": subscribers,
    }
    for mid in mailings:
        rows = svc.store.read(select(Recipient.uid).where(Recipient.mailing_uid == mid))
        ids = [UUID(row["uid"]) for row in rows]
        svc.store.write(
            [
                delete(DeliveryEvent).where(DeliveryEvent.recipient_uid.in_(ids)),
                delete(AuditEvent).where(AuditEvent.record_uid.in_([mid, *ids])),
                delete(Recipient).where(Recipient.mailing_uid == mid),
                delete(Mailing).where(Mailing.uid == mid),
            ]
        )
    if subscribers:
        svc.store.write(
            [
                delete(AuditEvent).where(AuditEvent.record_uid.in_(subscribers)),
                delete(Subscriber).where(Subscriber.uid.in_(subscribers)),
            ]
        )
    for uid in people:
        base.store.write(
            [
                delete(BaseAudit).where(BaseAudit.record_uid == uid),
                delete(BASE["parties"]).where(BASE["parties"].uid == uid),
            ]
        )
