"""Portable CRM resource projections for the Base adoption runtime."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import String, cast, func, or_, select

from src.erp.crm.contracts import validate_payload
from src.erp.crm.metatables import MODELS
from src.erp.crm.repositories.errors import ResourceNotFound
from src.erp.crm.repositories.resources.catalog import ORDER_COLUMNS, RESOURCE_SPECS


def table(logical):
    return MODELS[logical].__table__


class Reads:
    def __init__(self, store):
        self.store = store

    def raw(self, resource, uid):
        t = table(RESOURCE_SPECS[resource].logical_table)
        rows = self.store.read(select(t).where(t.c.uid == UUID(str(uid))))
        if not rows:
            raise ResourceNotFound(f"{resource} record not found")
        return rows[0]

    def detail(self, resource, uid):
        return self.project(resource, self.raw(resource, uid))

    def count(self, statement):
        return int(self.store.read(statement)[0]["count"])

    def project(self, resource, row, *, collection=False):
        row = dict(row)
        uid = UUID(str(row["uid"]))
        if resource == "contacts":
            co, tags, tasks = table("company"), table("contact_tag"), table("task")
            company = (
                self.store.read(select(co.c.name).where(co.c.uid == UUID(row["company_uid"])))
                if row["company_uid"]
                else []
            )
            row.update(
                display_name=" ".join(row[k] for k in ("first_name", "last_name") if row[k]),
                company_name=company[0]["name"] if company else None,
                tag_uids=[
                    r["tag_uid"]
                    for r in self.store.read(
                        select(tags.c.tag_uid)
                        .where(tags.c.contact_uid == uid)
                        .order_by(tags.c.tag_uid),
                        max_rows=100,
                    )
                ],
                open_task_count=self.count(
                    select(func.count().label("count"))
                    .select_from(tasks)
                    .where(
                        tasks.c.contact_uid == uid,
                        tasks.c.completed_at.is_(None),
                        tasks.c.archived_at.is_(None),
                    )
                ),
            )
        elif resource == "companies":
            contacts, affiliations, deals = (
                table("contact"),
                table("contact_company_affiliation"),
                table("deal"),
            )
            active = (
                select(affiliations.c.uid)
                .where(
                    affiliations.c.contact_uid == contacts.c.uid,
                    affiliations.c.company_uid == uid,
                    affiliations.c.archived_at.is_(None),
                    affiliations.c.status == "current",
                )
                .exists()
            )
            row.update(
                contact_count=self.count(
                    select(func.count().label("count"))
                    .select_from(contacts)
                    .where(contacts.c.archived_at.is_(None), active)
                ),
                deal_count=self.count(
                    select(func.count().label("count"))
                    .select_from(deals)
                    .where(deals.c.company_uid == uid)
                ),
            )
        elif resource == "deals":
            links = table("deal_contact")
            row["contact_uids"] = [
                item["contact_uid"]
                for item in self.store.read(
                    select(links.c.contact_uid)
                    .where(links.c.deal_uid == uid)
                    .order_by(links.c.contact_uid),
                    max_rows=100,
                )
            ]
            if row["amount"] is not None:
                row["amount"] = format(Decimal(str(row["amount"])), "f")
        elif resource == "activity":
            row = {
                k: row[k]
                for k in (
                    "uid",
                    "entity_type",
                    "entity_uid",
                    "kind",
                    "occurred_at",
                    "recorded_at",
                    "actor_uid",
                    "origin",
                    "summary",
                    "changes",
                )
            }
        spec = RESOURCE_SPECS[resource]
        if collection and resource == "prompts":
            row.pop("content_markdown", None)
        return validate_payload(
            spec.collection_contract if collection and spec.collection_contract else spec.contract,
            row,
        )

    def collection(self, resource, scope):
        spec = RESOURCE_SPECS[resource]
        t = table(spec.logical_table)
        predicates = []
        archived = scope.filters.get("archived", False)
        if "archived_at" in t.c and archived != "all":
            predicates.append(
                t.c.archived_at.is_not(None) if archived else t.c.archived_at.is_(None)
            )
        if scope.search:
            predicates.append(
                or_(
                    *(
                        func.lower(cast(t.c[field], String)).contains(
                            scope.search.lower(), autoescape=True
                        )
                        for field in spec.search_fields
                    )
                )
            )
        for field, value in scope.filters.items():
            key = "sector_key" if field == "sector" else field
            if field == "archived":
                continue
            if key in t.c:
                predicates.append(t.c[key] == (UUID(str(value)) if key.endswith("_uid") else value))
            elif field == "tag_uid":
                tags = table("contact_tag")
                predicates.append(
                    select(tags.c.uid)
                    .where(tags.c.contact_uid == t.c.uid, tags.c.tag_uid == UUID(str(value)))
                    .exists()
                )
            elif field == "has_open_tasks":
                tasks = table("task")
                expr = (
                    select(tasks.c.uid)
                    .where(
                        tasks.c.contact_uid == t.c.uid,
                        tasks.c.archived_at.is_(None),
                        tasks.c.completed_at.is_(None),
                    )
                    .exists()
                )
                predicates.append(expr if value else ~expr)
            elif field == "contact_uid" and resource == "deals":
                links = table("deal_contact")
                predicates.append(
                    select(links.c.uid)
                    .where(links.c.deal_uid == t.c.uid, links.c.contact_uid == UUID(str(value)))
                    .exists()
                )
            elif field == "completion" and resource == "tasks":
                if value not in ("open", "completed"):
                    raise ValueError("Unsupported task completion filter")
                predicates.append(
                    t.c.completed_at.is_(None) if value == "open" else t.c.completed_at.is_not(None)
                )
            else:
                raise ValueError(f"Unsupported {resource} filter: {field}")
        ordering = scope.ordering or spec.default_ordering
        key = ordering.removeprefix("-")
        if key not in ORDER_COLUMNS[resource]:
            raise ValueError("Unsupported ordering")
        order = (
            t.c[key].desc().nulls_last()
            if ordering.startswith("-")
            else t.c[key].asc().nulls_last()
        )
        count = self.count(select(func.count().label("count")).select_from(t).where(*predicates))
        rows = self.store.read(
            select(t)
            .where(*predicates)
            .order_by(order, t.c.uid)
            .limit(scope.page_size)
            .offset(scope.page_index * scope.page_size),
            max_rows=scope.page_size,
        )
        return {
            "items": [self.project(resource, row, collection=True) for row in rows],
            "pageInfo": {
                "pageIndex": scope.page_index,
                "pageSize": scope.page_size,
                "totalItems": count,
                "hasNextPage": (scope.page_index + 1) * scope.page_size < count,
                "hasPreviousPage": scope.page_index > 0,
            },
        }
