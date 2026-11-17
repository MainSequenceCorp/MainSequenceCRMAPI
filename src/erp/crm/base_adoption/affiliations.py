"""Portable employment history commands preserving partial-date precision."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import insert, select, update

from metatables.compiled_sql.v1 import GuardedStatement
from src.erp.crm.contracts import validate_payload
from src.erp.crm.models.affiliations import (
    AffiliationCreate,
    AffiliationFields,
    AffiliationTransition,
    period_bounds,
)
from src.erp.crm.repositories.errors import ResourceConflict, ResourceNotFound

from .reads import table
from .resources import Resources, activity, common


class Affiliations(Resources):
    def affiliation_detail(self, contact_uid, affiliation_uid):
        rows = self._rows(contact_uid, affiliation_uid=affiliation_uid)
        if not rows:
            raise ResourceNotFound("Affiliation not found")
        return rows[0]

    def _rows(self, contact_uid, *, affiliation_uid=None, offset=0, limit=101):
        a, c = table("contact_company_affiliation"), table("company")
        fields = [
            "uid",
            "contact_uid",
            "company_uid",
            "version",
            "status",
            "is_primary",
            "started_period",
            "ended_period",
            "job_title",
        ]
        query = (
            select(*(a.c[k] for k in fields), c.c.name.label("company_name"))
            .join(c, c.c.uid == a.c.company_uid)
            .where(a.c.contact_uid == UUID(str(contact_uid)), a.c.archived_at.is_(None))
        )
        if affiliation_uid:
            query = query.where(a.c.uid == UUID(str(affiliation_uid)))
        rows = self.store.read(
            query.order_by(a.c.is_primary.desc(), a.c.started_period.desc().nulls_last(), a.c.uid)
            .limit(limit)
            .offset(offset),
            max_rows=limit,
        )
        return [validate_payload("Affiliation", row) for row in rows]

    def affiliations(self, contact_uid, page_index=0, page_size=25):
        if page_index < 0 or not 1 <= page_size <= 100:
            raise ValueError("Invalid affiliation page")
        rows = self._rows(contact_uid, offset=page_index * page_size, limit=page_size + 1)
        return {
            "items": rows[:page_size],
            "next_page_index": page_index + 1 if len(rows) > page_size else None,
        }

    def create_affiliation(self, actor_uid, contact_uid, payload):
        data = AffiliationCreate.model_validate(payload).model_dump(mode="json")
        actor, contact_uid = UUID(str(actor_uid)), UUID(str(contact_uid))
        old = self.reads.raw("contacts", contact_uid)
        if old["archived_at"] or old["version"] != data["expected_contact_version"]:
            raise ResourceConflict("Contact changed or is archived")
        if data["is_primary"] and old["company_uid"]:
            raise ResourceConflict("The contact already has a primary company")
        row = {
            **common(uuid4(), actor),
            **{k: data[k] for k in AffiliationFields.model_fields},
            "contact_uid": contact_uid,
        }
        row["company_uid"] = UUID(str(row["company_uid"]))
        steps = [
            self.guard("contact", contact_uid, old["version"], active=True),
            self.guard("company", row["company_uid"], active=True),
        ]
        steps.extend(self.identity(actor, "affiliations", row, new=True))
        steps.append(insert(table("contact_company_affiliation")).values(**row))
        c = table("contact")
        values = dict(
            version=c.c.version + 1, updated_at=datetime.now(timezone.utc), updated_by_uid=actor
        )
        if row["is_primary"]:
            values["company_uid"] = row["company_uid"]
        steps.extend(
            [
                update(c).where(c.c.uid == contact_uid).values(**values),
                activity(actor, "contact", contact_uid, "affiliation-created"),
            ]
        )
        self.store.write(steps)
        return self.affiliation_detail(contact_uid, row["uid"])

    def patch_affiliation(self, actor_uid, contact_uid, affiliation_uid, payload):
        data = validate_payload("AffiliationPatch", payload)
        actor, contact_uid, uid = (
            UUID(str(actor_uid)),
            UUID(str(contact_uid)),
            UUID(str(affiliation_uid)),
        )
        old = self.affiliation_detail(contact_uid, uid)
        values = AffiliationFields.model_validate(
            {**{k: old[k] for k in AffiliationFields.model_fields}, **data["changes"]}
        ).model_dump(mode="json")
        row = {**old, **values, "version": old["version"] + 1}
        steps = [
            self.guard("contact", contact_uid, data["expected_contact_version"], active=True),
            self.guard("contact_company_affiliation", uid, data["expected_version"], active=True),
        ]
        steps.extend(self.identity(actor, "affiliations", row))
        a, c = table("contact_company_affiliation"), table("contact")
        changed = {k: values[k] for k in ("status", "started_period", "ended_period", "job_title")}
        now = datetime.now(timezone.utc)
        steps.extend(
            [
                update(a)
                .where(a.c.uid == uid)
                .values(**changed, version=a.c.version + 1, updated_at=now, updated_by_uid=actor),
                update(c)
                .where(c.c.uid == contact_uid)
                .values(version=c.c.version + 1, updated_at=now, updated_by_uid=actor),
                activity(actor, "contact", contact_uid, "affiliation-updated"),
            ]
        )
        self.store.write(steps)
        return self.affiliation_detail(contact_uid, uid)

    def transition_company(self, actor_uid, contact_uid, payload):
        data = AffiliationTransition.model_validate(payload).model_dump(mode="json")
        actor, contact_uid = UUID(str(actor_uid)), UUID(str(contact_uid))
        current = self.reads.raw("contacts", contact_uid)
        timeline = self.affiliations(contact_uid, 0, 1)["items"]
        primary = timeline[0] if timeline and timeline[0]["is_primary"] else None
        if current["version"] != data["expected_contact_version"] or current["archived_at"]:
            raise ResourceConflict("Contact changed or is archived")
        if bool(primary) != (data["previous_status"] is not None):
            raise ValueError("Specify how the previous primary affiliation should continue")
        if (str(primary["company_uid"]) if primary else None) != current["company_uid"]:
            raise ResourceConflict("Primary affiliation and contact projection disagree")
        if (
            primary
            and data["previous_status"] == "current"
            and str(data["new_company_uid"]) == str(primary["company_uid"])
        ):
            raise ValueError("Select a different company or end the previous period")
        if (
            primary
            and primary["started_period"]
            and data["previous_ended_period"]
            and period_bounds(primary["started_period"])[0]
            > period_bounds(data["previous_ended_period"])[1]
        ):
            raise ValueError("Previous end period precedes its start period")
        steps = [self.guard("contact", contact_uid, current["version"], active=True)]
        a, c = table("contact_company_affiliation"), table("contact")
        now = datetime.now(timezone.utc)
        if primary:
            row = {
                **primary,
                "status": data["previous_status"],
                "is_primary": False,
                "ended_period": data["previous_ended_period"],
                "version": primary["version"] + 1,
            }
            steps.extend(self.identity(actor, "affiliations", row))
            steps.append(
                GuardedStatement(
                    update(a)
                    .where(a.c.uid == UUID(primary["uid"]), a.c.version == primary["version"])
                    .values(
                        status=row["status"],
                        is_primary=False,
                        ended_period=row["ended_period"],
                        version=row["version"],
                        updated_at=now,
                        updated_by_uid=actor,
                    ),
                    expect_rows=1,
                    label="primary_affiliation",
                )
            )
        target = UUID(str(data["new_company_uid"])) if data["new_company_uid"] else None
        if target:
            steps.append(self.guard("company", target, active=True))
            row = {
                **common(uuid4(), actor),
                "contact_uid": contact_uid,
                "company_uid": target,
                "status": "current",
                "is_primary": True,
                "started_period": data["new_started_period"],
                "ended_period": None,
                "job_title": data["new_job_title"],
            }
            steps.extend(self.identity(actor, "affiliations", row, new=True))
            steps.append(insert(a).values(**row))
        steps.extend(
            [
                update(c)
                .where(c.c.uid == contact_uid)
                .values(
                    company_uid=target,
                    version=c.c.version + 1,
                    updated_at=now,
                    updated_by_uid=actor,
                ),
                activity(actor, "contact", contact_uid, "company-transition"),
            ]
        )
        self.store.write(steps)
        return self.reads.detail("contacts", contact_uid)
