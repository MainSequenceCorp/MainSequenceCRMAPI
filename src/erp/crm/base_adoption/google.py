"""Reviewed Google contact creation joins Base and source attribution atomically."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import insert, select

from metatables.compiled_sql.v1 import GuardedStatement
from src.erp.crm.contracts import normalized_create

from .reads import table
from .resources import Resources


def import_contact(
    store,
    *,
    actor_uid,
    source_connection_uid,
    external_id,
    payload_hash,
    action,
    target_uid,
    expected_version,
    values,
):
    actor, source = UUID(str(actor_uid)), UUID(str(source_connection_uid))
    oauth = table("google_oauth_connection")
    steps = [
        GuardedStatement(
            select(oauth.c.uid)
            .where(
                oauth.c.actor_uid == actor,
                oauth.c.source_connection_uid == source,
                oauth.c.status == "connected",
            )
            .with_for_update(),
            expect_rows=1,
            label="connected_google_source",
        )
    ]
    resources = Resources(store)
    if action == "create":
        if target_uid is not None:
            raise ValueError("Create cannot specify a target")
        payload = normalized_create(
            "contact",
            {
                key: values[key]
                for key in ("first_name", "last_name", "emails", "phones")
                if key in values
            },
        )
        creation, uid = resources.plan_create("contacts", actor, payload)
        steps.extend(creation[:-1])  # The import activity below records this command.
        version = 1
    elif action == "link":
        if target_uid is None:
            raise ValueError("Link requires a CRM target")
        uid = UUID(str(target_uid))
        existing = resources.reads.raw("contacts", uid)
        version = existing["version"]
        if expected_version is not None and version != expected_version:
            from src.erp.crm.repositories.errors import ResourceConflict

            raise ResourceConflict("The reviewed contact changed")
        steps.append(resources.guard("contact", uid, version, active=True))
    else:
        raise ValueError("Contact updates require the CRM contact editor")
    now, command = datetime.now(timezone.utc), uuid4()
    steps.extend(
        [
            insert(table("source_identity")).values(
                uid=uuid4(),
                source_connection_uid=source,
                entity_type="contact",
                external_id=external_id,
                target_uid=uid,
                source_payload_hash=payload_hash,
                source_updated_at=None,
                last_imported_target_version=version,
                last_import_job_uid=command,
                created_at=now,
                updated_at=now,
            ),
            insert(table("activity_event")).values(
                uid=uuid4(),
                entity_type="contact",
                entity_uid=uid,
                kind="imported",
                occurred_at=now,
                recorded_at=now,
                actor_uid=actor,
                origin="import",
                command_uid=command,
                summary="Reviewed Google import",
                changes={},
                source_attribution={"source": "google_workspace"},
            ),
        ]
    )
    store.write(steps)
    return uid
