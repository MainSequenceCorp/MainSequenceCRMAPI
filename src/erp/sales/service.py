"""Atomic Sales aggregate operations; exact amounts and explicit lifecycle."""

from datetime import date, datetime, timezone
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext
from uuid import UUID, uuid4

from sqlalchemy import delete, func, insert, or_, select, update

from mainsequence.client.exceptions import BadRequestError
from metatables import MetaTableTransactionGuardError
from metatables.compiled_sql.v1 import GuardedStatement

from .errors import SalesError
from .metatables import AuditEvent, Order, OrderLine
from .schemas import OrderInput


class Service:
    def __init__(self, store, actor_uid, capabilities, dependencies):
        self.store, self.actor_uid, self.capabilities, self.dependencies = (
            store,
            UUID(str(actor_uid)),
            set(capabilities),
            dependencies,
        )

    def require(self, capability):
        if capability not in self.capabilities:
            raise SalesError(403, "forbidden", "Sales access does not permit this operation")

    def get(self, uid):
        self.require("sales.read")
        uid = UUID(str(uid))
        rows = self.store.read(select(Order.__table__).where(Order.uid == uid).limit(1))
        if not rows:
            raise SalesError(404, "not_found", "Sales order not found")
        return {
            **rows[0],
            "lines": self.store.read(
                select(OrderLine.__table__)
                .where(OrderLine.order_uid == uid)
                .order_by(OrderLine.position)
                .limit(100)
            ),
        }

    def collection(self, *, page_index=0, page_size=25, search="", state=None):
        self.require("sales.read")
        terms = []
        if search:
            terms.append(
                or_(
                    func.lower(Order.name).contains(search.lower(), autoescape=True),
                    func.lower(Order.customer_name).contains(search.lower(), autoescape=True),
                )
            )
        if state:
            terms.append(Order.state == state)
        total = int(
            self.store.read(select(func.count().label("count")).select_from(Order).where(*terms))[
                0
            ]["count"]
        )
        items = self.store.read(
            select(Order.__table__)
            .where(*terms)
            .order_by(Order.created_at.desc(), Order.uid)
            .offset(page_index * page_size)
            .limit(page_size),
            max_rows=page_size,
        )
        return {
            "items": items,
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
            raise SalesError(
                409, "conflict", "Order changed; reload and review before retrying"
            ) from exc
        except BadRequestError as exc:
            detail = (getattr(exc, "payload", {}) or {}).get("detail", {})
            if isinstance(detail, dict) and detail.get("code") == "compiled_sql_database_error":
                raise SalesError(
                    409,
                    "constraint_conflict",
                    "This reference or request already exists; check the saved order",
                ) from exc
            raise

    def audit(self, uid, action, version, fields):
        return insert(AuditEvent).values(
            uid=uuid4(),
            record_uid=uid,
            actor_uid=self.actor_uid,
            action=action,
            version=version,
            occurred_at=datetime.now(timezone.utc),
            fields=sorted(fields),
        )

    def prepare(self, data, uid):
        customer = self.dependencies.get("base", "parties", data.customer_uid)
        company = self.dependencies.get("base", "operating-companies", data.operating_company_uid)
        currency = self.dependencies.get("base", "currencies", data.currency_uid)
        deal = (
            self.dependencies.opportunity(data.crm_deal_uid, data.customer_uid)
            if data.crm_deal_uid
            else None
        )
        lines = []
        with localcontext() as ctx:
            ctx.prec = 80
            quantum = Decimal(1).scaleb(-currency["minor_units"])
            rounding = ROUND_HALF_EVEN if currency["rounding"] == "half_even" else ROUND_HALF_UP
            for position, line in enumerate(data.lines, 1):
                item = self.dependencies.get("catalog", "items", line.item_uid)
                if not item["saleable"]:
                    raise SalesError(
                        422, "not_saleable", "Every line item must be available for sale"
                    )
                unit = self.dependencies.get("catalog", "units", item["unit_uid"])
                self.dependencies.get("catalog", "unit-groups", unit["group_uid"])
                self.dependencies.get("catalog", "categories", item["category_uid"])
                amount = (
                    Decimal(line.quantity)
                    * Decimal(line.unit_price)
                    * (1 - Decimal(line.discount) / 100)
                ).quantize(quantum, rounding=rounding)
                lines.append(
                    {
                        **line.model_dump(),
                        "uid": uuid4(),
                        "order_uid": uid,
                        "position": position,
                        "unit_uid": UUID(item["unit_uid"]),
                        "description": line.description or item["sale_description"] or item["name"],
                        "net_total": format(amount, "f"),
                        "snapshot": {
                            "item_name": item["name"],
                            "item_code": item["code"],
                            "kind": item["kind"],
                            "item_version": item["version"],
                            "unit_name": unit["name"],
                            "unit_code": unit["code"],
                            "unit_version": unit["version"],
                        },
                    }
                )
            total = sum((Decimal(line["net_total"]) for line in lines), Decimal(0)).quantize(
                quantum
            )
        values = data.model_dump(exclude={"lines"})
        values.update(
            customer_name=customer["name"],
            company_name=company["name"],
            currency_code=currency["code"],
            net_total=format(total, "f"),
            crm_deal_name=(deal.get("name") or deal.get("title") or str(data.crm_deal_uid))
            if deal
            else None,
            snapshot={
                "customer_version": customer["version"],
                "company_version": company["version"],
                "currency_version": currency["version"],
                "minor_units": currency["minor_units"],
                "rounding": currency["rounding"],
            },
        )
        return values, lines

    def save(self, payload, *, request_uid=None, uid=None, expected_version=None):
        self.require("sales.write")
        data = OrderInput.model_validate(payload)
        creating = uid is None
        if creating and not request_uid:
            raise SalesError(422, "request_required", "A request identifier is required")
        uid = UUID(str(request_uid if creating else uid))
        if not creating:
            row = self.get(uid)
            if row["version"] != expected_version:
                raise SalesError(409, "conflict", "Order changed; reload and review")
            if row["state"] != "draft":
                raise SalesError(409, "locked", "Only a draft quotation can be edited")
        values, lines = self.prepare(data, uid)
        now = datetime.now(timezone.utc)
        version = 1 if creating else expected_version + 1
        values.update(version=version, updated_at=now, updated_by_uid=self.actor_uid)
        if creating:
            steps = [
                insert(Order).values(
                    **values,
                    uid=uid,
                    state="draft",
                    downstream={},
                    created_at=now,
                    created_by_uid=self.actor_uid,
                    confirmed_at=None,
                )
            ]
        else:
            steps = [
                GuardedStatement(
                    update(Order)
                    .where(
                        Order.uid == uid, Order.version == expected_version, Order.state == "draft"
                    )
                    .values(**values)
                    .returning(Order.uid),
                    expect_rows=1,
                    label="order_version",
                ),
                delete(OrderLine).where(OrderLine.order_uid == uid),
            ]
        if lines:
            steps.append(insert(OrderLine).values(lines))
        self.transact(
            [*steps, self.audit(uid, "create" if creating else "update", version, values.keys())]
        )
        return self.get(uid)

    def transition(self, uid, action, expected_version):
        self.require("sales.write")
        uid = UUID(str(uid))
        row = self.get(uid)
        if row["version"] != expected_version:
            raise SalesError(409, "conflict", "Order changed; reload and review")
        transitions = {
            "quoted": ({"draft"}, "quoted"),
            "confirm": ({"draft", "quoted"}, "confirmed"),
            "cancel": ({"draft", "quoted", "confirmed"}, "cancelled"),
            "reopen": ({"cancelled", "quoted"}, "draft"),
        }
        if action not in transitions:
            raise SalesError(404, "not_found", "Unknown Sales action")
        allowed, target = transitions[action]
        if row["state"] not in allowed:
            raise SalesError(
                409, "invalid_state", "This action is not available in the current state"
            )
        if row["downstream"] and action in {"cancel", "reopen"}:
            raise SalesError(
                409, "downstream_records", "Related records must be resolved before cancellation"
            )
        values = {}
        steps = []
        if action in {"quoted", "confirm"}:
            if not row["lines"]:
                raise SalesError(
                    422, "empty_order", "Add at least one line before quoting or confirming"
                )
            if (
                row["valid_until"]
                and date.fromisoformat(str(row["valid_until"])[:10])
                < datetime.now(timezone.utc).date()
            ):
                raise SalesError(
                    422, "expired", "The quotation has expired; revise its validity in draft"
                )
            payload = {k: row[k] for k in OrderInput.model_fields if k != "lines"}
            payload["lines"] = [
                {
                    k: line[k]
                    for k in ("item_uid", "description", "quantity", "unit_price", "discount")
                }
                for line in row["lines"]
            ]
            values, lines = self.prepare(OrderInput.model_validate(payload), uid)
            # Preserve line identities once allocated, especially at confirmation.
            for old, line in zip(row["lines"], lines):
                line["uid"] = UUID(old["uid"])
            steps = [
                delete(OrderLine).where(OrderLine.order_uid == uid),
                insert(OrderLine).values(lines),
            ]
        values.update(
            state=target,
            version=expected_version + 1,
            updated_at=datetime.now(timezone.utc),
            updated_by_uid=self.actor_uid,
        )
        if action == "confirm":
            values["confirmed_at"] = datetime.now(timezone.utc)
        if action == "reopen":
            values["confirmed_at"] = None
        self.transact(
            [
                GuardedStatement(
                    update(Order)
                    .where(
                        Order.uid == uid,
                        Order.version == expected_version,
                        Order.state == row["state"],
                    )
                    .values(**values)
                    .returning(Order.uid),
                    expect_rows=1,
                    label="order_version",
                ),
                *steps,
                self.audit(uid, action, expected_version + 1, values.keys()),
            ]
        )
        return self.get(uid)

    def attach(self, uid, expected_version, consumer, record_uid):
        """Public owner command for explicitly authorized later integrations."""
        self.require("sales.configure")
        uid = UUID(str(uid))
        row = self.get(uid)
        if consumer not in {"finance", "projects", "inventory", "commerce"}:
            raise SalesError(422, "consumer", "Unknown Sales integration")
        key = f"{consumer}:{UUID(str(record_uid))}"
        if row["state"] != "confirmed":
            raise SalesError(
                409, "invalid_state", "Only confirmed orders accept downstream records"
            )
        if key in row["downstream"]:
            return row
        links = {**row["downstream"], key: True}
        self.transact(
            [
                GuardedStatement(
                    update(Order)
                    .where(
                        Order.uid == uid,
                        Order.version == expected_version,
                        Order.state == "confirmed",
                    )
                    .values(
                        downstream=links,
                        version=expected_version + 1,
                        updated_at=datetime.now(timezone.utc),
                        updated_by_uid=self.actor_uid,
                    )
                    .returning(Order.uid),
                    expect_rows=1,
                    label="order_version",
                ),
                self.audit(uid, "link", expected_version + 1, ["downstream"]),
            ]
        )
        return self.get(uid)
