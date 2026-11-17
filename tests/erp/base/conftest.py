"""All Base integration writes use the real, verified local MetaTables API."""

import uuid

import pytest
from sqlalchemy import delete

from api.erp.base.identity import ALL_CAPABILITIES
from mainsequence.client import User
from metatables import configure_local_client, upgrade_application
from src.erp.base.metatables import RESOURCES, Allocation, AuditEvent
from src.erp.base.seed import seed
from src.erp.base.service import Service
from src.erp.base.store import Store, require_local_runtime


@pytest.fixture(scope="session")
def base_service():
    configure_local_client()
    require_local_runtime()
    upgrade_application("src.erp.base.migrations:migration")
    actor = User.get_authenticated_user_details()
    service = Service(Store(local_only=True), actor.uid, ALL_CAPABILITIES)
    seed(service)
    return service


@pytest.fixture
def records(base_service):
    created = []

    def create(resource, data):
        row = base_service.save(resource, data)
        created.append((resource, uuid.UUID(row["uid"])))
        return row

    yield create
    # Delete only this test's explicit fixture IDs, in reverse dependency order.
    for resource, uid in reversed(created):
        steps = [delete(AuditEvent.__table__).where(AuditEvent.record_uid == uid)]
        if resource == "number-sequences":
            steps.insert(0, delete(Allocation.__table__).where(Allocation.sequence_uid == uid))
        steps.append(delete(RESOURCES[resource].__table__).where(RESOURCES[resource].uid == uid))
        base_service.store.write(steps)
