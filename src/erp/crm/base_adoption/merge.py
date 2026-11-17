"""CRM merge keeps business history and releases, rather than merges, Base identities."""

from datetime import datetime, timezone
from uuid import UUID, uuid4, uuid5

from sqlalchemy import String, case, cast, delete, func, insert, literal, or_, select, update

from metatables.compiled_sql.v1 import GuardedStatement
from src.erp.base.consumer_commands import detach_party, move_owned_affiliations
from src.erp.crm.contracts import validate_payload
from src.erp.crm.repositories.contacts.merge import ContactMerge
from src.erp.crm.repositories.errors import ResourceConflict

from .affiliations import Affiliations
from .commands import service
from .reads import Reads, table
from .resources import Resources, typed_values


class Merge(ContactMerge):
    def __init__(self, store):
        self.store = store
        self.reads = Reads(store)
        self.contact_affiliations = Affiliations(store)
        self.resources = Resources(store)

    def _merge_context(self, survivor_uid, loser_uid):
        pair = [UUID(str(survivor_uid)), UUID(str(loser_uid))]
        enrolled = table("campaign_participant")
        if self.store.read(select(enrolled.c.uid).where(enrolled.c.contact_uid.in_(pair)).limit(1)):
            raise ResourceConflict("Contacts enrolled in a Campaign cannot be merged")
        leads = table("solution_selling_lead")
        lead_rows = self.store.read(
            select(leads.c.uid, leads.c.version)
            .where(leads.c.contact_uid.in_(pair))
            .order_by(leads.c.uid),
            max_rows=2,
        )
        if len(lead_rows) > 1:
            raise ResourceConflict(
                "Both Contacts have Leads; consolidate their Lead context before merging"
            )
        counts = {}
        for label, logical, field in [
            ("notes", "note", "contact_uid"),
            ("tasks", "task", "contact_uid"),
            ("deals", "deal_contact", "contact_uid"),
            ("tags", "contact_tag", "contact_uid"),
            ("source_identities", "source_identity", "target_uid"),
            ("affiliations", "contact_company_affiliation", "contact_uid"),
        ]:
            t = table(logical)
            query = select(func.count().label("count")).select_from(t).where(t.c[field] == pair[1])
            if logical == "source_identity":
                query = query.where(t.c.entity_type == "contact")
            counts[label] = int(self.store.read(query)[0]["count"])
        return counts, lead_rows

    def bounded(self, query):
        rows = self.store.read(query.limit(1001), max_rows=1001)
        if len(rows) > 1000:
            raise ResourceConflict(
                "This merge exceeds 1000 related rows; review it in a controlled data migration"
            )
        return rows

    def merge_contacts(self, actor_uid, survivor_uid, command):
        actor, survivor_uid, loser_uid = (
            UUID(str(actor_uid)),
            UUID(str(survivor_uid)),
            UUID(command["loser_uid"]),
        )
        preview = self._merge_plan(survivor_uid, loser_uid, command["field_resolutions"])
        if (
            preview["survivor_version"] != command["expected_version"]
            or preview["loser_version"] != command["loser_expected_version"]
            or preview["plan_hash"] != command["plan_hash"]
        ):
            raise ResourceConflict("Contact merge preview is stale")
        proposed = preview["proposed_contact"]
        base = service(self.store, actor)
        r = self.resources
        now, command_uid = datetime.now(timezone.utc), uuid4()
        steps = [
            r.guard("contact", survivor_uid, preview["survivor_version"], active=True),
            r.guard("contact", loser_uid, preview["loser_version"], active=True),
        ]
        participant = table("campaign_participant")
        steps.append(
            GuardedStatement(
                select(participant.c.uid)
                .where(participant.c.contact_uid.in_([survivor_uid, loser_uid]))
                .with_for_update(),
                expect_rows=0,
                label="no_campaign_enrollment",
            )
        )
        steps.extend(r.identity(actor, "contacts", proposed))
        steps.extend(detach_party(base, loser_uid, "crm"))
        c = table("contact")
        fields = typed_values(c, proposed)
        for key in (
            "uid",
            "created_at",
            "created_by_uid",
            "archived_at",
            "version",
            "updated_at",
            "updated_by_uid",
        ):
            fields.pop(key, None)
        steps.append(
            update(c)
            .where(c.c.uid == survivor_uid)
            .values(**fields, version=c.c.version + 1, updated_at=now, updated_by_uid=actor)
        )
        for logical, field in [("contact_tag", "tag_uid"), ("deal_contact", "deal_uid")]:
            t = table(logical)
            rows = self.bounded(select(t).where(t.c.contact_uid.in_([survivor_uid, loser_uid])))
            # Fence the complete set before replacing duplicate links.
            steps.append(
                GuardedStatement(
                    select(t.c.uid)
                    .where(t.c.contact_uid.in_([survivor_uid, loser_uid]))
                    .with_for_update(),
                    expect_rows=len(rows),
                    label=logical + "_count",
                )
            )
            refs = {row[field] for row in rows}
            steps.append(delete(t).where(t.c.contact_uid.in_([survivor_uid, loser_uid])))
            if refs:
                steps.append(
                    insert(t).values(
                        [
                            dict(
                                uid=uuid5(survivor_uid, f"{logical}:{ref}"),
                                contact_uid=survivor_uid,
                                **{field: UUID(ref)},
                                created_at=now,
                            )
                            for ref in refs
                        ]
                    )
                )
        for logical in (
            "note",
            "task",
            "email_thread",
            "solution_selling_lead",
            "solution_selling_diagnosis",
        ):
            t = table(logical)
            steps.append(
                update(t)
                .where(t.c.contact_uid == loser_uid)
                .values(
                    contact_uid=survivor_uid,
                    version=t.c.version + 1,
                    updated_at=now,
                    updated_by_uid=actor,
                )
            )
        identities = table("source_identity")
        steps.append(
            update(identities)
            .where(identities.c.entity_type == "contact", identities.c.target_uid == loser_uid)
            .values(target_uid=survivor_uid, updated_at=now)
        )
        a = table("contact_company_affiliation")
        relations = self.bounded(select(a).where(a.c.contact_uid.in_([survivor_uid, loser_uid])))
        moving = [row for row in relations if row["contact_uid"] == str(loser_uid)]
        steps.extend(
            move_owned_affiliations(
                base, loser_uid, survivor_uid, [row["uid"] for row in moving], "crm"
            )
        )
        chosen_company = proposed["company_uid"]
        own_primary = any(
            row["contact_uid"] == str(survivor_uid)
            and row["company_uid"] == chosen_company
            and row["is_primary"]
            and not row["archived_at"]
            for row in relations
        )
        if relations:
            primary = {}
            for row in relations:
                keep = row["is_primary"] and row["company_uid"] == chosen_company
                if row["contact_uid"] == str(loser_uid):
                    keep = keep and not own_primary
                primary[UUID(row["uid"])] = keep
            predicate = or_(
                *(
                    (a.c.uid == UUID(row["uid"])) & (a.c.version == row["version"])
                    for row in relations
                )
            )
            steps.append(
                GuardedStatement(
                    update(a)
                    .where(predicate)
                    .values(
                        contact_uid=survivor_uid,
                        is_primary=case(primary, value=a.c.uid, else_=False),
                        version=a.c.version + 1,
                        updated_at=now,
                        updated_by_uid=actor,
                    ),
                    expect_rows=len(relations),
                    label="merge_affiliation_versions",
                )
            )
        # Participants are structured JSON. Keep its source ordering and avoid duplicate participants.
        interactions = table("interaction")
        # Governed SQLite does not grant access to json_each's virtual table.
        # Text narrows candidates; exact structured matching below determines edits.
        candidates = self.bounded(
            select(interactions).where(
                cast(interactions.c.participants, String).contains(str(loser_uid), autoescape=True)
            )
        )
        people = [
            row
            for row in candidates
            if any(person.get("contact_uid") == str(loser_uid) for person in row["participants"])
        ]
        if people:
            replacements = {}
            for row in people:
                has_survivor = any(
                    person.get("contact_uid") == str(survivor_uid) for person in row["participants"]
                )
                result = []
                for person in row["participants"]:
                    if person.get("contact_uid") == str(loser_uid):
                        if has_survivor:
                            continue
                        person = {**person, "contact_uid": str(survivor_uid)}
                    result.append(person)
                replacements[UUID(row["uid"])] = literal(
                    result, type_=interactions.c.participants.type
                )
            predicate = or_(
                *(
                    (interactions.c.uid == UUID(row["uid"]))
                    & (interactions.c.version == row["version"])
                    for row in people
                )
            )
            steps.append(
                GuardedStatement(
                    update(interactions)
                    .where(predicate)
                    .values(
                        participants=case(replacements, value=interactions.c.uid),
                        version=interactions.c.version + 1,
                        updated_at=now,
                        updated_by_uid=actor,
                    ),
                    expect_rows=len(people),
                    label="merge_interaction_versions",
                )
            )
        links = table("base_identity_link")
        steps.extend(
            [
                update(links)
                .where(links.c.resource == "contacts", links.c.record_uid == loser_uid)
                .values(state="retired"),
                delete(c).where(c.c.uid == loser_uid),
                insert(table("entity_redirect")).values(
                    uid=uuid5(command_uid, "redirect"),
                    entity_type="contact",
                    from_uid=loser_uid,
                    to_uid=survivor_uid,
                    created_at=now,
                    command_uid=command_uid,
                ),
                insert(table("activity_event")).values(
                    uid=uuid5(command_uid, "activity"),
                    entity_type="contact",
                    entity_uid=survivor_uid,
                    kind="merged",
                    occurred_at=now,
                    recorded_at=now,
                    actor_uid=actor,
                    origin="live",
                    command_uid=command_uid,
                    summary="Merged contacts",
                    changes={
                        "retired_uid": str(loser_uid),
                        "field_resolutions": command["field_resolutions"],
                    },
                    source_attribution=None,
                ),
            ]
        )
        self.store.write(steps)
        return validate_payload(
            "MergeResult",
            {
                "command_uid": str(command_uid),
                "survivor": self.reads.detail("contacts", survivor_uid),
                "retired_uid": str(loser_uid),
            },
        )
