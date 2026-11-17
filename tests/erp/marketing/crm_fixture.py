"""Owned local CRM adoption/read fixture; production Marketing never writes CRM."""

from contextlib import contextmanager
from uuid import UUID, uuid4

import httpx
from sqlalchemy import delete, insert


@contextmanager
def crm_followup_fixture(svc, party):
    from src.erp.crm.base_adoption.reads import table
    from src.erp.crm.base_adoption.resources import common, typed_values
    from src.erp.crm.base_adoption.store import Store
    from src.erp.crm.platform.catalog import configured_registry

    configured_registry.cache_clear()
    store = Store(configured_registry())
    assert str(store.data_source_uid) == svc.store.data_source_uid
    contact_uid = UUID(party["uid"])
    task_uid = uuid4()
    try:
        with httpx.Client(base_url="http://127.0.0.1:38641/api/crm/v1/", timeout=30) as client:
            response = client.post(
                "contacts/adopt/",
                json={"party_uid": str(contact_uid), "expected_party_version": party["version"]},
            )
            assert response.status_code == 201, response.text
            # Existing CRM generic task writes use PostgreSQL-specific legacy SQL.
            # This owned governed SQLite fixture verifies the actual public read/link
            # contract, not task creation portability or a new Marketing task command.
            model = table("task")
            store.write(
                [
                    insert(model).values(
                        **typed_values(
                            model,
                            {
                                **common(task_uid, svc.actor_uid),
                                "contact_uid": contact_uid,
                                "type_key": "",
                                "text": "Marketing local follow-up " + uuid4().hex[:10],
                            },
                        )
                    )
                ]
            )
            response = client.get(f"tasks/{task_uid}/")
            assert response.status_code == 200, response.text
            yield response.json()
    finally:
        steps = []
        for logical, field, uid in [
            ("activity_event", "entity_uid", task_uid),
            ("task", "uid", task_uid),
            ("activity_event", "entity_uid", contact_uid),
            ("base_identity_link", "record_uid", contact_uid),
            ("contact", "uid", contact_uid),
        ]:
            t = table(logical)
            steps.append(delete(t).where(t.c[field] == uid))
        store.write(steps)
