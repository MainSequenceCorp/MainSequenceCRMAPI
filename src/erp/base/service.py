"""Deterministic Base operations with atomic version, reference and audit fences."""

from datetime import datetime, timezone
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import and_, func, insert, select, update

from mainsequence.client.exceptions import BadRequestError
from metatables import MetaTableTransactionGuardError
from metatables.compiled_sql.v1 import GuardedStatement
from src.erp.base.metatables import RESOURCES, Allocation, AuditEvent
from src.erp.base.schemas import INPUTS


class BaseError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


class Service:
    def __init__(self, store, actor_uid, capabilities):
        self.store, self.actor_uid, self.capabilities = (
            store,
            UUID(str(actor_uid)),
            set(capabilities),
        )

    def require(self, capability):
        if capability not in self.capabilities:
            raise BaseError(403, "forbidden", "Base access does not permit this operation")

    def table(self, resource):
        if resource not in RESOURCES:
            raise BaseError(404, "not_found", "Unknown Base resource")
        return RESOURCES[resource].__table__

    def scope(self, resource):
        table = self.table(resource)
        return table.c.actor_uid == self.actor_uid if resource == "preferences" else True

    def permission(self, resource):
        return (
            "base.read"
            if resource == "preferences"
            else "base.write"
            if resource in {"parties", "affiliations", "addresses"}
            else "base.configure"
        )

    def get(self, resource, uid):
        self.require("base.read")
        table = self.table(resource)
        rows = self.store.read(
            select(table).where(table.c.uid == UUID(str(uid)), self.scope(resource)).limit(1)
        )
        if not rows:
            raise BaseError(404, "not_found", "Base record not found")
        return rows[0]

    def collection(self, resource, *, page_index=0, page_size=25, search="", archived=False):
        self.require("base.read")
        table = self.table(resource)
        predicates = [
            self.scope(resource),
            table.c.archived_at.is_not(None) if archived else table.c.archived_at.is_(None),
        ]
        if search:
            predicates.append(func.lower(table.c.name).contains(search.lower(), autoescape=True))
        total = int(
            self.store.read(
                select(func.count().label("count")).select_from(table).where(*predicates)
            )[0]["count"]
        )
        rows = self.store.read(
            select(table)
            .where(*predicates)
            .order_by(table.c.name, table.c.uid)
            .offset(page_index * page_size)
            .limit(page_size),
            max_rows=page_size,
        )
        return {
            "items": rows,
            "pageInfo": {
                "pageIndex": page_index,
                "pageSize": page_size,
                "totalItems": total,
                "hasNextPage": (page_index + 1) * page_size < total,
                "hasPreviousPage": page_index > 0,
            },
        }

    def audit(self, resource, uid, action, version, fields):
        return insert(AuditEvent.__table__).values(
            uid=uuid4(),
            resource=resource,
            record_uid=uid,
            action=action,
            version=version,
            actor_uid=self.actor_uid,
            occurred_at=datetime.now(timezone.utc),
            fields=sorted(fields),
        )

    def transact(self, steps):
        try:
            return self.store.write(steps)
        except MetaTableTransactionGuardError as exc:
            raise BaseError(
                409,
                "conflict",
                "Record version, active reference or dependent records changed; reload and review",
            ) from exc
        except BadRequestError as exc:
            # Only a reported database constraint failure is a user conflict.
            payload = getattr(exc, "payload", {}) or {}
            detail = payload.get("detail", {})
            code = detail.get("code") if isinstance(detail, dict) else payload.get("code")
            if code == "compiled_sql_database_error":
                raise BaseError(
                    409,
                    "constraint_conflict",
                    "A unique code or record relationship conflicts with existing data",
                ) from exc
            raise

    def reference_guards(self, resource, data, uid):
        table = self.table(resource)
        guards = []
        for column in table.columns:
            value = data.get(column.name)
            if value is None:
                continue
            for fk in column.foreign_keys:
                target = fk.column.table
                predicate = and_(target.c.uid == value, target.c.archived_at.is_(None))
                if resource == "affiliations":
                    predicate = and_(
                        predicate,
                        target.c.kind
                        == ("person" if column.name == "person_uid" else "organization"),
                    )
                elif resource == "operating-companies" and column.name == "party_uid":
                    predicate = and_(predicate, target.c.kind == "organization")
                if resource == "addresses" and column.name == "subdivision_uid":
                    predicate = and_(predicate, target.c.country_uid == data["country_uid"])
                if resource == "subdivisions" and column.name == "country_uid":
                    predicate = and_(predicate, target.c.code == data["code"].split("-")[0])
                guards.append(
                    GuardedStatement(
                        select(target.c.uid).where(predicate).with_for_update(),
                        expect_rows=1,
                        label="active_reference",
                    )
                )
        if resource == "operating-companies" and data.get("parent_uid"):
            parent = UUID(str(data["parent_uid"]))
            seen = {uid}
            while parent:
                if parent in seen or len(seen) > 16:
                    raise BaseError(
                        422,
                        "invalid_parent",
                        "Operating-company hierarchy must be acyclic and at most 16 levels",
                    )
                seen.add(parent)
                ancestor = self.get(resource, parent)
                guards.append(
                    GuardedStatement(
                        select(table.c.uid)
                        .where(table.c.uid == parent, table.c.version == ancestor["version"])
                        .with_for_update(),
                        expect_rows=1,
                        label="parent_version",
                    )
                )
                parent = UUID(ancestor["parent_uid"]) if ancestor["parent_uid"] else None
        return guards

    def save(self, resource, payload, *, uid=None, expected_version=None):
        self.require(self.permission(resource))
        data = INPUTS[resource].model_validate(payload).model_dump(mode="python")
        if resource == "parties":
            data["emails"] = [str(email) for email in data["emails"]]
        table = self.table(resource)
        creating = uid is None
        if creating:
            uid = (
                uuid5(NAMESPACE_URL, "erp-base:settings")
                if resource == "settings"
                else uuid5(NAMESPACE_URL, f"erp-base:preferences:{self.actor_uid}")
                if resource == "preferences"
                else uuid4()
            )
        else:
            uid = UUID(str(uid))
        now = datetime.now(timezone.utc)
        if resource == "settings":
            data["key"] = "default"
        if resource == "preferences":
            data["actor_uid"] = self.actor_uid
        if not creating:
            old = self.get(resource, uid)
            if old["archived_at"]:
                raise BaseError(409, "archived", "Restore this record before editing")
            for field in (
                "code",
                "kind",
                "party_uid" if resource == "operating-companies" else "code",
                "operating_company_uid" if resource == "number-sequences" else "code",
            ):
                if field in data and str(data[field]) != str(old[field]):
                    raise BaseError(422, "immutable_field", f"{field} cannot change after creation")
            if expected_version != old["version"]:
                raise BaseError(409, "stale_version", "The record changed; reload before saving")
        version = 1 if creating else expected_version + 1
        values = {**data, "updated_at": now, "updated_by_uid": self.actor_uid, "version": version}
        guards = self.reference_guards(resource, data, uid)
        if creating:
            values.update(uid=uid, created_at=now, created_by_uid=self.actor_uid, archived_at=None)
            if resource == "number-sequences":
                values["next_number"] = 1
            write = insert(table).values(**values)
        else:
            write = GuardedStatement(
                update(table)
                .where(
                    table.c.uid == uid,
                    table.c.version == expected_version,
                    table.c.archived_at.is_(None),
                    self.scope(resource),
                )
                .values(**values),
                expect_rows=1,
                label="record_version",
            )
        rows = self.transact(
            [
                *guards,
                write,
                self.audit(resource, uid, "create" if creating else "update", version, data),
                select(table).where(table.c.uid == uid),
            ]
        )
        return rows[0]

    def archive(self, resource, uid, expected_version, *, restore=False):
        self.require(self.permission(resource))
        if resource in {"settings", "preferences"}:
            raise BaseError(
                422, "unsupported", "Defaults and personal preferences cannot be archived"
            )
        table, uid = self.table(resource), UUID(str(uid))
        record = self.get(resource, uid)
        if bool(record["archived_at"]) != restore:
            raise BaseError(409, "archive_state", "The record is already in the requested state")
        now = datetime.now(timezone.utc)
        steps = [
            GuardedStatement(
                update(table)
                .where(table.c.uid == uid, table.c.version == expected_version)
                .values(
                    archived_at=None if restore else now,
                    version=expected_version + 1,
                    updated_at=now,
                    updated_by_uid=self.actor_uid,
                ),
                expect_rows=1,
                label="archive_version",
            )
        ]
        if restore:
            data = (
                INPUTS[resource]
                .model_validate({k: record[k] for k in INPUTS[resource].model_fields})
                .model_dump(mode="python")
            )
            steps.extend(self.reference_guards(resource, data, uid))
        else:
            for model in RESOURCES.values():
                dependent = model.__table__
                for column in dependent.columns:
                    for fk in column.foreign_keys:
                        if fk.column.table is table:
                            steps.append(
                                GuardedStatement(
                                    select(dependent.c.uid)
                                    .where(column == uid, dependent.c.archived_at.is_(None))
                                    .limit(1),
                                    expect_rows=0,
                                    label="active_dependents",
                                )
                            )
        steps.extend(
            [
                self.audit(
                    resource,
                    uid,
                    "restore" if restore else "archive",
                    expected_version + 1,
                    ["archived_at"],
                ),
                select(table).where(table.c.uid == uid),
            ]
        )
        return self.transact(steps)[0]

    def allocation_retry(self, sequence_uid, request_uid):
        allocations = Allocation.__table__
        existing = self.store.read(select(allocations).where(allocations.c.uid == request_uid))
        if existing:
            if existing[0]["sequence_uid"] != str(sequence_uid) or existing[0]["actor_uid"] != str(
                self.actor_uid
            ):
                raise BaseError(
                    409,
                    "request_reused",
                    "This allocation request belongs to another sequence or actor",
                )
            return existing[0]
        return None

    def allocate(self, sequence_uid, request_uid, expected_version):
        self.require("base.write")
        sequence_uid, request_uid = UUID(str(sequence_uid)), UUID(str(request_uid))
        allocations = Allocation.__table__
        previous = self.allocation_retry(sequence_uid, request_uid)
        if previous:
            return previous
        sequence = self.get("number-sequences", sequence_uid)
        if sequence["archived_at"] or sequence["version"] != expected_version:
            previous = self.allocation_retry(sequence_uid, request_uid)
            if previous:
                return previous
            raise BaseError(409, "stale_version", "The sequence changed; reload before allocating")
        counter = int(sequence["next_number"])
        table = self.table("number-sequences")
        values = {
            "uid": request_uid,
            "sequence_uid": sequence_uid,
            "number": counter,
            "value": f"{sequence['prefix']}{counter:0{sequence['padding']}d}",
            "actor_uid": self.actor_uid,
            "created_at": datetime.now(timezone.utc),
        }
        try:
            return self.transact(
                [
                    GuardedStatement(
                        update(table)
                        .where(
                            table.c.uid == sequence_uid,
                            table.c.version == expected_version,
                            table.c.archived_at.is_(None),
                        )
                        .values(
                            next_number=counter + 1,
                            version=expected_version + 1,
                            updated_at=values["created_at"],
                            updated_by_uid=self.actor_uid,
                        ),
                        expect_rows=1,
                        label="sequence_version",
                    ),
                    insert(allocations).values(**values),
                    self.audit(
                        "number-sequences",
                        sequence_uid,
                        "allocate",
                        expected_version + 1,
                        ["next_number"],
                    ),
                    select(allocations).where(allocations.c.uid == request_uid),
                ]
            )[0]
        except BaseError as error:
            if error.status == 409:
                previous = self.allocation_retry(sequence_uid, request_uid)
                if previous:
                    return previous
            raise

    def round_amount(self, uid, amount):
        currency = self.get("currencies", uid)
        if currency["archived_at"]:
            raise BaseError(409, "archived", "Currency is archived")
        with localcontext() as ctx:
            ctx.prec = 40
            value = Decimal(amount).quantize(
                Decimal(1).scaleb(-currency["minor_units"]),
                rounding=ROUND_HALF_EVEN if currency["rounding"] == "half_even" else ROUND_HALF_UP,
            )
        return {
            "currency_uid": currency["uid"],
            "code": currency["code"],
            "currency_version": currency["version"],
            "amount": format(value, "f"),
        }
