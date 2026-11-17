import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select

from mainsequence.client import User
from metatables import configure_local_client, upgrade_application
from src.erp.collaboration.dependencies import Dependencies
from src.erp.collaboration.metatables import AuditEvent, Discussion, Message, MessageRevision
from src.erp.collaboration.service import Service
from src.erp.collaboration.store import Store, require_local_runtime


@pytest.fixture(scope="session")
def collaboration_service():
    configure_local_client()
    expected = os.environ.get("COLLABORATION_LOCAL_SOURCE_UID")
    assert expected and str(require_local_runtime()) == expected
    upgrade_application("src.erp.collaboration.migrations:migration")
    actor = User.get_authenticated_user_details().uid
    return Service(
        Store(local_only=True),
        actor,
        {"collaboration.read", "collaboration.write", "collaboration.manage"},
        Dependencies(),
        actor_name="Verified local author",
    )


@pytest.fixture
def discussions(collaboration_service):
    svc = collaboration_service
    owned = []

    def new(**changes):
        uid = uuid4()
        owned.append(uid)
        return svc.create(
            {
                "request_uid": uid,
                "name": "Discussion " + uuid4().hex[:10],
                "scope": "shared",
                "audience": "collaboration_readers",
                **changes,
            }
        )

    yield {"service": svc, "new": new, "owned": owned}
    if owned:
        rows = svc.store.read(select(Message.uid).where(Message.discussion_uid.in_(owned)))
        mids = [UUID(row["uid"]) for row in rows]
        svc.store.write(
            [
                delete(MessageRevision).where(MessageRevision.message_uid.in_(mids)),
                delete(Message).where(Message.discussion_uid.in_(owned)),
                delete(AuditEvent).where(AuditEvent.record_uid.in_(owned)),
                delete(Discussion).where(Discussion.uid.in_(owned)),
            ]
        )
