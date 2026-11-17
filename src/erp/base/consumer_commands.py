"""Public Base commands for a module detaching or moving its own usage claims."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import insert, or_, select, update

from metatables.compiled_sql.v1 import GuardedStatement

from .metatables import Affiliation, AuditEvent, Party
from .service import BaseError


def detach_party(service, uid, consumer):
    service.require("base.write")
    uid = UUID(str(uid))
    row = service.get("parties", uid)
    claims = dict(row["consumers"])
    if consumer not in claims:
        raise BaseError(409, "missing_claim", "The profile is no longer attached")
    del claims[consumer]
    return [
        GuardedStatement(
            update(Party)
            .where(Party.uid == uid, Party.version == row["version"])
            .values(
                consumers=claims,
                version=row["version"] + 1,
                updated_at=datetime.now(timezone.utc),
                updated_by_uid=service.actor_uid,
            ),
            expect_rows=1,
            label="detach_consumer_version",
        ),
        service.audit("parties", uid, "update", row["version"] + 1, ["consumers"]),
    ]


def move_owned_affiliations(service, source_uid, target_uid, affiliation_uids, consumer):
    service.require("base.write")
    source_uid, target_uid = UUID(str(source_uid)), UUID(str(target_uid))
    uids = [UUID(str(uid)) for uid in affiliation_uids]
    if not uids:
        return []
    rows = service.store.read(
        select(Affiliation.__table__).where(Affiliation.uid.in_(uids)), max_rows=len(uids)
    )
    if len(rows) != len(uids) or any(
        str(row["person_uid"]) != str(source_uid) or set(row["consumers"]) != {consumer}
        for row in rows
    ):
        raise BaseError(
            409,
            "shared_relationship",
            "A relationship is used outside this module; review shared identity separately",
        )
    # Every source version is fenced; a concurrent Directory edit rolls back the merge.
    predicate = or_(
        *(
            (Affiliation.uid == UUID(row["uid"])) & (Affiliation.version == row["version"])
            for row in rows
        )
    )
    audits = []
    from uuid import uuid4

    now = datetime.now(timezone.utc)
    for row in rows:
        audits.append(
            dict(
                uid=uuid4(),
                resource="affiliations",
                record_uid=UUID(row["uid"]),
                action="update",
                version=row["version"] + 1,
                actor_uid=service.actor_uid,
                occurred_at=now,
                fields=["person_uid"],
            )
        )
    return [
        GuardedStatement(
            select(Party.uid)
            .where(Party.uid == target_uid, Party.kind == "person", Party.archived_at.is_(None))
            .with_for_update(),
            expect_rows=1,
            label="merge_target_identity",
        ),
        GuardedStatement(
            update(Affiliation)
            .where(predicate)
            .values(
                person_uid=target_uid,
                version=Affiliation.version + 1,
                updated_at=now,
                updated_by_uid=service.actor_uid,
            ),
            expect_rows=len(rows),
            label="shared_affiliation_versions",
        ),
        insert(AuditEvent).values(audits),
    ]
