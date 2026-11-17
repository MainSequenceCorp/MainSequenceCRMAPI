"""Atomic profile commands: Base owns identity, CRM owns its compatibility projection."""

import json
from datetime import datetime, timezone
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import DateTime, Uuid, delete, insert, select, update

from metatables.compiled_sql.v1 import GuardedStatement
from src.erp.crm.repositories.errors import ResourceConflict
from src.erp.crm.repositories.resources.catalog import RESOURCE_SPECS

from .commands import identity_plan
from .mapping import affiliation_input, party_input
from .reads import Reads, table


def typed_values(t, values):
    result = {}
    for key, value in values.items():
        if key not in t.c:
            continue
        if value is not None:
            if isinstance(t.c[key].type, Uuid):
                value = UUID(str(value))
            elif isinstance(t.c[key].type, DateTime) and isinstance(value, str):
                value = datetime.fromisoformat(value)
        result[key] = value
    return result


def common(uid, actor, *, version=1):
    now = datetime.now(timezone.utc)
    return dict(
        uid=uid,
        created_at=now,
        updated_at=now,
        created_by_uid=actor,
        updated_by_uid=actor,
        version=version,
        archived_at=None,
    )


def activity(actor, logical, uid, kind, changes=None):
    now, command = datetime.now(timezone.utc), uuid4()
    return insert(table("activity_event")).values(
        uid=uuid5(command, "activity"),
        entity_type=logical,
        entity_uid=uid,
        kind=kind,
        occurred_at=now,
        recorded_at=now,
        actor_uid=actor,
        origin="live",
        command_uid=command,
        summary=f"{kind.title()} {logical}",
        changes=changes or {},
        source_attribution=None,
    )


def link_statement(actor, resource, row, *, state="active"):
    payload = (
        party_input(resource, row)
        if resource in ("contacts", "companies")
        else affiliation_input(row)
    )
    digest = sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()
    return insert(table("base_identity_link")).values(
        uid=uuid5(NAMESPACE_URL, f"crm-base:{resource}:{row['uid']}"),
        resource=resource,
        record_uid=UUID(str(row["uid"])),
        base_uid=UUID(str(row["uid"])),
        source_version=row["version"],
        source_digest=digest,
        state=state,
        created_at=datetime.now(timezone.utc),
        created_by_uid=actor,
    )


class Resources:
    def __init__(self, store):
        self.store, self.reads = store, Reads(store)

    def identity(self, actor, resource, row, *, new=False):
        steps = identity_plan(self.store, actor, resource, row)
        if new:
            steps.append(link_statement(actor, resource, row))
        return steps

    def guard(self, logical, uid, version=None, *, active=False):
        t = table(logical)
        predicates = [t.c.uid == UUID(str(uid))]
        if version is not None:
            predicates.append(t.c.version == version)
        if active:
            predicates.append(t.c.archived_at.is_(None))
        return GuardedStatement(
            select(t.c.uid).where(*predicates).with_for_update(),
            expect_rows=1,
            label=f"{logical}_version_or_reference",
        )

    def tag_steps(self, uid, values):
        links, tags = table("contact_tag"), table("tag")
        uids = [UUID(str(value)) for value in values]
        steps = [
            GuardedStatement(
                select(tags.c.uid)
                .where(tags.c.uid.in_(uids), tags.c.archived_at.is_(None))
                .with_for_update(),
                expect_rows=len(uids),
                label="active_tags",
            ),
            delete(links).where(links.c.contact_uid == uid),
        ]
        if uids:
            steps.append(
                insert(links).values(
                    [
                        dict(
                            uid=uuid5(uid, str(tag)),
                            contact_uid=uid,
                            tag_uid=tag,
                            created_at=datetime.now(timezone.utc),
                        )
                        for tag in uids
                    ]
                )
            )
        return steps

    def company_change(self, actor, uid, previous, target):
        steps = []
        a = table("contact_company_affiliation")
        if str(previous) == str(target):
            return steps
        if target:
            steps.append(self.guard("company", target, active=True))
        primaries = self.store.read(
            select(a).where(
                a.c.contact_uid == uid, a.c.is_primary.is_(True), a.c.archived_at.is_(None)
            )
        )
        if previous and (len(primaries) != 1 or str(primaries[0]["company_uid"]) != str(previous)):
            raise ResourceConflict("Primary company and affiliation history disagree")
        for old in primaries:
            changed = {
                **old,
                "status": "former",
                "is_primary": False,
                "version": old["version"] + 1,
            }
            steps.extend(self.identity(actor, "affiliations", changed))
            steps.append(
                GuardedStatement(
                    update(a)
                    .where(a.c.uid == UUID(old["uid"]), a.c.version == old["version"])
                    .values(
                        status="former",
                        is_primary=False,
                        version=changed["version"],
                        updated_at=datetime.now(timezone.utc),
                        updated_by_uid=actor,
                    ),
                    expect_rows=1,
                    label="prior_affiliation",
                )
            )
        if target:
            new = {
                **common(uuid4(), actor),
                "contact_uid": uid,
                "company_uid": UUID(str(target)),
                "status": "current",
                "is_primary": True,
                "started_period": None,
                "ended_period": None,
                "job_title": None,
            }
            steps.extend(self.identity(actor, "affiliations", new, new=True))
            steps.append(insert(a).values(**new))
        return steps

    def create(self, resource, actor_uid, data):
        steps, uid = self.plan_create(resource, actor_uid, data)
        self.store.write(steps)
        return self.reads.detail(resource, uid)

    def plan_create(self, resource, actor_uid, data):
        from src.erp.crm.repositories.resources.writes import ResourceMutations

        actor, uid = UUID(str(actor_uid)), uuid4()
        values = ResourceMutations._create_values(resource, dict(data), actor)
        tags = values.pop("tag_uids", []) if resource == "contacts" else None
        t = table(RESOURCE_SPECS[resource].logical_table)
        row = {**common(uid, actor), **typed_values(t, values)}
        steps = self.identity(actor, resource, row, new=True)
        if resource == "contacts" and row["company_uid"]:
            steps.append(self.guard("company", row["company_uid"], active=True))
        steps.append(insert(t).values(**row))
        if tags is not None:
            steps.extend(self.tag_steps(uid, tags))
            steps.extend(self.company_change(actor, uid, None, row["company_uid"]))
        steps.append(activity(actor, RESOURCE_SPECS[resource].logical_table, uid, "created"))
        return steps, uid

    def update(self, resource, actor_uid, uid, expected_version, data):
        actor, uid = UUID(str(actor_uid)), UUID(str(uid))
        t = table(RESOURCE_SPECS[resource].logical_table)
        old = self.reads.raw(resource, uid)
        if old["version"] != expected_version:
            raise ResourceConflict("Record version changed")
        values = typed_values(t, data)
        row = {
            **old,
            **values,
            "version": expected_version + 1,
            "updated_at": datetime.now(timezone.utc),
            "updated_by_uid": actor,
        }
        steps = [self.guard(RESOURCE_SPECS[resource].logical_table, uid, expected_version)]
        steps.extend(self.identity(actor, resource, row))
        if resource == "contacts":
            if "tag_uids" in data:
                steps.extend(self.tag_steps(uid, data["tag_uids"]))
            if "company_uid" in data:
                steps.extend(
                    self.company_change(actor, uid, old["company_uid"], row["company_uid"])
                )
        steps.append(
            GuardedStatement(
                update(t)
                .where(t.c.uid == uid, t.c.version == expected_version)
                .values(
                    **values,
                    version=expected_version + 1,
                    updated_at=row["updated_at"],
                    updated_by_uid=actor,
                ),
                expect_rows=1,
                label="profile_version",
            )
        )
        steps.append(activity(actor, RESOURCE_SPECS[resource].logical_table, uid, "updated", data))
        self.store.write(steps)
        return self.reads.detail(resource, uid)

    def archive(self, resource, actor_uid, uid, expected_version, archived):
        actor, uid = UUID(str(actor_uid)), UUID(str(uid))
        t = table(RESOURCE_SPECS[resource].logical_table)
        old = self.reads.raw(resource, uid)
        if old["version"] != expected_version:
            raise ResourceConflict("Record version changed")
        now = datetime.now(timezone.utc)
        row = {**old, "archived_at": now if archived else None, "version": expected_version + 1}
        steps = [self.guard(RESOURCE_SPECS[resource].logical_table, uid, expected_version)]
        steps.extend(self.identity(actor, resource, row))
        steps.extend(
            [
                update(t)
                .where(t.c.uid == uid)
                .values(
                    archived_at=row["archived_at"],
                    version=row["version"],
                    updated_at=now,
                    updated_by_uid=actor,
                ),
                activity(
                    actor,
                    RESOURCE_SPECS[resource].logical_table,
                    uid,
                    "archived" if archived else "restored",
                ),
            ]
        )
        self.store.write(steps)
        return self.reads.detail(resource, uid)

    def adopt(self, resource, actor_uid, party_uid, expected_party_version):
        from src.erp.base.schemas import PartyInput
        from src.erp.crm.repositories.resources.writes import ResourceMutations

        from .commands import service
        from .mapping import party_projection

        actor, uid = UUID(str(actor_uid)), UUID(str(party_uid))
        base = service(self.store, actor)
        party = base.get("parties", uid)
        expected_kind = "person" if resource == "contacts" else "organization"
        if party["kind"] != expected_kind or party["archived_at"]:
            raise ResourceConflict("Choose an active Directory identity of the matching kind")
        if party["version"] != expected_party_version:
            raise ResourceConflict("Directory identity changed; reload before adoption")
        if "crm" in party["consumers"]:
            raise ResourceConflict("This identity already has a CRM profile")
        links = table("base_identity_link")
        if self.store.read(
            select(links.c.uid).where(links.c.resource == resource, links.c.record_uid == uid)
        ):
            raise ResourceConflict(
                "This CRM identity was retired by a merge; use its surviving profile"
            )
        projection = party_projection(resource, party)
        from src.erp.crm.contracts import normalized_create

        normalized = normalized_create(
            "contact" if resource == "contacts" else "company",
            {key: value for key, value in projection.items() if key != "normalized_domain"},
        )
        if resource == "companies":
            normalized["normalized_domain"] = projection.get("normalized_domain")
        t = table(RESOURCE_SPECS[resource].logical_table)
        values = ResourceMutations._create_values(resource, normalized, actor)
        values.pop("tag_uids", None)
        row = {**common(uid, actor), **typed_values(t, values)}
        claims = {
            **party["consumers"],
            "crm": {
                "uid": str(uid),
                "logical": RESOURCE_SPECS[resource].logical_table,
                "active": True,
            },
        }
        payload = {key: party[key] for key in PartyInput.model_fields}
        steps, _ = base.plan_save(
            "parties",
            payload,
            uid=uid,
            expected_version=expected_party_version,
            claims=claims,
            skip_consumer="crm",
        )
        steps.extend(
            [
                insert(t).values(**row),
                link_statement(actor, resource, row),
                activity(actor, RESOURCE_SPECS[resource].logical_table, uid, "created"),
            ]
        )
        self.store.write(steps)
        return self.reads.detail(resource, uid)
