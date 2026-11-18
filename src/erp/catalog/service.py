"""Catalog business operations through atomic governed MetaTables commands."""

from datetime import datetime, timezone
from decimal import Decimal, localcontext
from fractions import Fraction
from uuid import UUID, uuid4

from sqlalchemy import func, insert, or_, select, update

from mainsequence.client.exceptions import BadRequestError
from metatables import MetaTableTransactionGuardError
from metatables.compiled_sql.v1 import GuardedStatement
from src.erp.catalog.metatables import RESOURCES, AuditEvent, Category, Item, Unit, UnitGroup
from src.erp.catalog.schemas import INPUTS, ConvertInput
from src.erp.module_access import require_module


class CatalogError(Exception):
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
        require_module("catalog")
        if capability not in self.capabilities:
            raise CatalogError(403, "forbidden", "Catalog access does not permit this operation")

    def table(self, resource):
        if resource not in RESOURCES:
            raise CatalogError(404, "not_found", "Unknown Catalog resource")
        return RESOURCES[resource].__table__

    def permission(self, resource):
        return "catalog.write" if resource == "items" else "catalog.configure"

    def get(self, resource, uid):
        self.require("catalog.read")
        table = self.table(resource)
        rows = self.store.read(select(table).where(table.c.uid == UUID(str(uid))).limit(1))
        if not rows:
            raise CatalogError(404, "not_found", "Catalog record not found")
        return rows[0]

    def collection(
        self,
        resource,
        *,
        page_index=0,
        page_size=25,
        search="",
        archived=False,
        kind=None,
        group_uid=None,
    ):
        self.require("catalog.read")
        table = self.table(resource)
        if (
            kind is not None
            and resource != "items"
            or group_uid is not None
            and resource != "units"
        ):
            raise CatalogError(
                422, "invalid_filter", "This filter is not supported for this resource"
            )
        predicates = [
            table.c.archived_at.is_not(None) if archived else table.c.archived_at.is_(None)
        ]
        if search:
            predicates.append(
                or_(
                    *(
                        func.lower(table.c[name]).contains(search.lower(), autoescape=True)
                        for name in ("name", "code")
                    )
                )
            )
        if kind:
            predicates.append(table.c.kind == kind)
        if group_uid:
            predicates.append(table.c.group_uid == UUID(str(group_uid)))
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

    def transact(self, steps):
        try:
            return self.store.write(steps)
        except MetaTableTransactionGuardError as exc:
            raise CatalogError(
                409, "conflict", "Record, active reference or dependents changed; reload and review"
            ) from exc
        except BadRequestError as exc:
            payload = getattr(exc, "payload", {}) or {}
            detail = payload.get("detail", {})
            code = detail.get("code") if isinstance(detail, dict) else payload.get("code")
            if code == "compiled_sql_database_error":
                raise CatalogError(
                    409,
                    "constraint_conflict",
                    "Code or relationship conflicts with an existing record",
                ) from exc
            raise

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

    def category_guards(self, parent_uid, *, uid=None, expected_version=None):
        """Validate a bounded ancestor chain and fence every read version in UID order."""
        table = Category.__table__
        seen, ancestors = ({str(uid)} if uid else set()), {}
        current = str(parent_uid) if parent_uid else None
        while current:
            if current in seen or len(seen) >= 16:
                raise CatalogError(
                    422,
                    "invalid_parent",
                    "Product categories must be acyclic and at most 16 levels deep",
                )
            seen.add(current)
            row = self.get("categories", current)
            ancestors[current] = row["version"]
            current = row["parent_uid"]
        if uid and expected_version:
            ancestors[str(uid)] = expected_version
        return [
            GuardedStatement(
                select(table.c.uid)
                .where(
                    table.c.uid == UUID(key),
                    table.c.version == version,
                    table.c.archived_at.is_(None),
                )
                .with_for_update(),
                expect_rows=1,
                label="category_ancestor",
            )
            for key, version in sorted(ancestors.items())
        ]

    def references(self, resource, data, *, uid=None, expected_version=None):
        refs, guards = [], []
        if resource == "categories":
            return self.category_guards(
                data.get("parent_uid"), uid=uid, expected_version=expected_version
            )
        if resource == "units":
            refs = [(UnitGroup.__table__, UUID(str(data["group_uid"])))]
        elif resource == "items":
            guards = self.category_guards(data["category_uid"])
            unit = self.get("units", data["unit_uid"])
            purchase = self.get("units", data["purchase_unit_uid"])
            if unit["group_uid"] != purchase["group_uid"]:
                raise CatalogError(
                    422,
                    "incompatible_units",
                    "Purchase and default units must belong to the same group",
                )
            refs = [(UnitGroup.__table__, UUID(unit["group_uid"]))] + [
                (Unit.__table__, UUID(key)) for key in sorted({unit["uid"], purchase["uid"]})
            ]
        guards += [
            GuardedStatement(
                select(t.c.uid).where(t.c.uid == key, t.c.archived_at.is_(None)).with_for_update(),
                expect_rows=1,
                label="active_reference",
            )
            for t, key in refs
        ]
        if resource == "units" and not data["is_reference"]:
            guards.append(
                GuardedStatement(
                    select(Unit.uid)
                    .where(
                        Unit.group_uid == UUID(str(data["group_uid"])),
                        Unit.is_reference.is_(True),
                        Unit.archived_at.is_(None),
                    )
                    .with_for_update(),
                    expect_rows=1,
                    label="reference_unit_required",
                )
            )
        return guards

    def save(self, resource, payload, *, uid=None, expected_version=None):
        self.require(self.permission(resource))
        data = INPUTS[resource].model_validate(payload).model_dump()
        if resource == "units":
            data["decimal_places"] = max(
                0, -Decimal(data["rounding_increment"]).as_tuple().exponent
            )
        if resource == "items":
            data["purchase_unit_uid"] = data["purchase_unit_uid"] or data["unit_uid"]
        table = self.table(resource)
        creating = uid is None
        uid = uuid4() if creating else UUID(str(uid))
        if not creating:
            previous = self.get(resource, uid)
            if resource == "units" and any(
                str(data[k]) != str(previous[k])
                for k in ("group_uid", "factor", "is_reference", "rounding_increment")
            ):
                raise CatalogError(
                    422,
                    "immutable_unit",
                    "A unit's group, factor and precision cannot change; create a new unit",
                )
            if resource == "items" and (
                any(
                    str(data[k]) != str(previous[k])
                    for k in ("kind", "unit_uid", "purchase_unit_uid")
                )
            ):
                raise CatalogError(
                    422,
                    "immutable_item",
                    "An item's kind and units cannot change; create a new item",
                )
            if (
                not expected_version
                or previous["version"] != expected_version
                or previous["archived_at"]
            ):
                raise CatalogError(
                    409, "conflict", "Record changed or is archived; reload and review"
                )
        now = datetime.now(timezone.utc)
        steps = self.references(resource, data, uid=uid, expected_version=expected_version)
        if (
            resource == "categories"
            and not creating
            and str(previous["parent_uid"]) != str(data["parent_uid"])
        ):
            steps.append(
                GuardedStatement(
                    select(Category.uid).where(Category.parent_uid == uid).limit(1),
                    expect_rows=0,
                    label="move_leaf_category",
                )
            )
        fields = (
            list(data) if creating else [k for k, v in data.items() if str(v) != str(previous[k])]
        )
        version = 1 if creating else expected_version + 1
        values = {**data, "version": version, "updated_at": now, "updated_by_uid": self.actor_uid}
        if creating:
            steps.append(
                insert(table).values(
                    **values,
                    uid=uid,
                    created_at=now,
                    created_by_uid=self.actor_uid,
                    archived_at=None,
                )
            )
        else:
            steps.append(
                GuardedStatement(
                    update(table)
                    .where(
                        table.c.uid == uid,
                        table.c.version == expected_version,
                        table.c.archived_at.is_(None),
                    )
                    .values(**values)
                    .returning(table.c.uid),
                    expect_rows=1,
                    label="version",
                )
            )
        return self.transact(
            [
                *steps,
                self.audit(resource, uid, "create" if creating else "update", version, fields),
                select(table).where(table.c.uid == uid),
            ]
        )[0]

    def archive(self, resource, uid, expected_version, *, restore=False):
        self.require(self.permission(resource))
        uid = UUID(str(uid))
        table = self.table(resource)
        previous = self.get(resource, uid)
        if previous["version"] != expected_version or bool(previous["archived_at"]) != restore:
            raise CatalogError(
                409, "conflict", "Record changed or already has the requested archive state"
            )
        # Lock the parent before checking dependents, matching reference-lock order.
        steps = [
            GuardedStatement(
                select(table.c.uid)
                .where(table.c.uid == uid, table.c.version == expected_version)
                .with_for_update(),
                expect_rows=1,
                label="version",
            )
        ]
        if restore:
            steps = [*self.references(resource, previous, uid=uid), *steps]
        else:
            dependents = []
            if resource == "unit-groups":
                dependents = [(Unit.__table__, Unit.group_uid == uid)]
            elif resource == "units":
                # Every unit state change locks its group first, as unit creation does.
                steps.insert(
                    0,
                    GuardedStatement(
                        select(UnitGroup.uid)
                        .where(UnitGroup.uid == UUID(previous["group_uid"]))
                        .with_for_update(),
                        expect_rows=1,
                        label="unit_group_lock",
                    ),
                )
                dependents = [
                    (Item.__table__, or_(Item.unit_uid == uid, Item.purchase_unit_uid == uid))
                ]
                if previous["is_reference"]:
                    dependents.append(
                        (
                            Unit.__table__,
                            (Unit.group_uid == UUID(previous["group_uid"])) & (Unit.uid != uid),
                        )
                    )
            elif resource == "categories":
                dependents = [
                    (Item.__table__, Item.category_uid == uid),
                    (Category.__table__, Category.parent_uid == uid),
                ]
            for target, predicate in dependents:
                steps.append(
                    GuardedStatement(
                        select(target.c.uid)
                        .where(predicate, target.c.archived_at.is_(None))
                        .limit(1),
                        expect_rows=0,
                        label="active_dependents",
                    )
                )
        version = expected_version + 1
        steps.extend(
            [
                GuardedStatement(
                    update(table)
                    .where(table.c.uid == uid, table.c.version == expected_version)
                    .values(
                        archived_at=None if restore else datetime.now(timezone.utc),
                        version=version,
                        updated_at=datetime.now(timezone.utc),
                        updated_by_uid=self.actor_uid,
                    )
                    .returning(table.c.uid),
                    expect_rows=1,
                    label="version",
                ),
                self.audit(
                    resource, uid, "restore" if restore else "archive", version, ["archived_at"]
                ),
                select(table).where(table.c.uid == uid),
            ]
        )
        return self.transact(steps)[0]

    def convert(self, payload):
        self.require("catalog.read")
        data = ConvertInput.model_validate(payload)
        source, target = self.get("units", data.from_unit_uid), self.get("units", data.to_unit_uid)
        if source["group_uid"] != target["group_uid"]:
            raise CatalogError(
                422, "incompatible_units", "Conversion requires units from the same unit group"
            )
        group = self.get("unit-groups", source["group_uid"])
        if source["archived_at"] or target["archived_at"] or group["archived_at"]:
            raise CatalogError(
                409, "archived_unit", "Conversion requires active units and unit group"
            )
        exact = (
            Fraction(Decimal(data.quantity))
            * Fraction(Decimal(source["factor"]))
            / Fraction(Decimal(target["factor"]))
        )
        increment = Decimal(target["rounding_increment"])
        steps = exact / Fraction(increment)
        quotient, remainder = divmod(abs(steps.numerator), steps.denominator)
        if data.rounding == "up":
            quotient += bool(remainder)
        elif 2 * remainder > steps.denominator or (
            2 * remainder == steps.denominator and (data.rounding == "half_up" or quotient % 2)
        ):
            quotient += 1
        with localcontext() as context:
            context.prec = 100
            rounded = Decimal(-quotient if steps < 0 else quotient) * increment
        return {
            "quantity": format(rounded, "f"),
            "rounded": exact != Fraction(rounded),
            "from_unit_uid": source["uid"],
            "to_unit_uid": target["uid"],
            "from_unit_version": source["version"],
            "to_unit_version": target["version"],
            "rounding": data.rounding,
            "rounding_increment": target["rounding_increment"],
        }
