"""Owned fixtures through the real local MetaTables API and SDK identity."""

import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete

from api.erp.catalog.identity import ALL_CAPABILITIES
from mainsequence.client import User
from metatables import configure_local_client, upgrade_application
from src.erp.catalog.metatables import RESOURCES, AuditEvent
from src.erp.catalog.service import Service
from src.erp.catalog.store import Store, require_local_runtime


@pytest.fixture(scope="session")
def catalog():
    expected = os.environ.get("CATALOG_LOCAL_SOURCE_UID")
    if not expected:
        pytest.fail("Set CATALOG_LOCAL_SOURCE_UID to the reviewed local SQLite source before tests")
    configure_local_client()
    assert str(require_local_runtime()) == expected
    upgrade_application("src.erp.catalog.migrations:migration")
    return Service(
        Store(local_only=True), User.get_authenticated_user_details().uid, ALL_CAPABILITIES
    )


@pytest.fixture
def records(catalog):
    owned = []

    def create(resource, **data):
        data = {
            "name": "Catalog test " + uuid4().hex[:8],
            "code": "TEST-" + uuid4().hex[:16].upper(),
            **data,
        }
        row = catalog.save(resource, data)
        owned.append((resource, UUID(row["uid"])))
        return row

    yield create
    for resource, uid in reversed(owned):
        catalog.store.write(
            [
                delete(AuditEvent.__table__).where(AuditEvent.record_uid == uid),
                delete(RESOURCES[resource].__table__).where(RESOURCES[resource].uid == uid),
            ]
        )


@pytest.fixture
def quantities(records):
    group = records("unit-groups")
    reference = records(
        "units", group_uid=group["uid"], is_reference=True, factor="1", rounding_increment="0.05"
    )
    dozen = records("units", group_uid=group["uid"], factor="12", rounding_increment="1")
    category = records("categories")
    item = records(
        "items",
        category_uid=category["uid"],
        unit_uid=reference["uid"],
        purchase_unit_uid=dozen["uid"],
        kind="product",
    )
    return group, reference, dozen, category, item
