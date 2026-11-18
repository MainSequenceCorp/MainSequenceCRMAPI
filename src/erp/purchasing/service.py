"""Atomic Purchasing aggregate operations; exact amounts and explicit lifecycle."""

from datetime import datetime, timezone
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction
from uuid import UUID, uuid4

from sqlalchemy import delete, func, insert, or_, select, update

from mainsequence.client.exceptions import BadRequestError
from metatables import MetaTableTransactionGuardError
from metatables.compiled_sql.v1 import GuardedStatement
from src.erp.module_access import require_module

from .errors import PurchasingError
from .metatables import AuditEvent, Order, OrderLine, Receipt
from .schemas import AcceptInput, BillInput, OrderInput, ReceiptInput


class Service:
    def __init__(self, store, actor_uid, capabilities, dependencies):
        self.store, self.actor_uid, self.capabilities, self.dependencies = (
            store,
            UUID(str(actor_uid)),
            set(capabilities),
            dependencies,
        )

    def require(self, capability):
        require_module("purchasing")
        if capability not in self.capabilities:
            raise PurchasingError(
                403, "forbidden", "Purchasing access does not permit this operation"
            )

    def get(self, uid):
        self.require("purchasing.read")
        uid = UUID(str(uid))
        rows = self.store.read(select(Order.__table__).where(Order.uid == uid).limit(1))
        if not rows:
            raise PurchasingError(404, "not_found", "Purchasing order not found")
        return {
            **rows[0],
            "receipts": self.store.read(
                select(Receipt.__table__).where(Receipt.order_uid == uid).limit(100)
            ),
            "lines": self.store.read(
                select(OrderLine.__table__)
                .where(OrderLine.order_uid == uid)
                .order_by(OrderLine.position)
                .limit(100)
            ),
        }

    def collection(self, *, page_index=0, page_size=25, search="", state=None):
        self.require("purchasing.read")
        terms = []
        if search:
            terms.append(
                or_(
                    func.lower(Order.name).contains(search.lower(), autoescape=True),
                    func.lower(Order.supplier_name).contains(search.lower(), autoescape=True),
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
            raise PurchasingError(
                409, "conflict", "Order changed; reload and review before retrying"
            ) from exc
        except BadRequestError as exc:
            detail = (getattr(exc, "payload", {}) or {}).get("detail", {})
            if isinstance(detail, dict) and detail.get("code") == "compiled_sql_database_error":
                raise PurchasingError(
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
        supplier = self.dependencies.get("base", "parties", data.supplier_uid)
        company = self.dependencies.get("base", "operating-companies", data.operating_company_uid)
        currency = self.dependencies.get("base", "currencies", data.currency_uid)
        lines = []
        with localcontext() as ctx:
            ctx.prec = 80
            quantum = Decimal(1).scaleb(-currency["minor_units"])
            rounding = ROUND_HALF_EVEN if currency["rounding"] == "half_even" else ROUND_HALF_UP
            for position, line in enumerate(data.lines, 1):
                item = self.dependencies.get("catalog", "items", line.item_uid)
                if not item["purchasable"]:
                    raise PurchasingError(
                        422, "not_purchasable", "Every line item must be available for purchase"
                    )
                unit = self.dependencies.get("catalog", "units", item["purchase_unit_uid"])
                self.dependencies.get("catalog", "unit-groups", unit["group_uid"])
                self.dependencies.get("catalog", "categories", item["category_uid"])
                stock_unit = self.dependencies.get("catalog", "units", item["unit_uid"])
                if unit["group_uid"] != stock_unit["group_uid"]:
                    raise PurchasingError(
                        422, "unit_group", "Purchase and stock units must be compatible"
                    )
                stock_quantity = (
                    Decimal(line.quantity) * Decimal(unit["factor"]) / Decimal(stock_unit["factor"])
                )
                if item["kind"] == "product":
                    ticks = stock_quantity / Decimal(stock_unit["rounding_increment"])
                    if (
                        Fraction(stock_quantity)
                        != Fraction(line.quantity)
                        * Fraction(unit["factor"])
                        / Fraction(stock_unit["factor"])
                        or ticks != ticks.to_integral_value()
                        or ticks > 10**12
                        or stock_quantity != stock_quantity.quantize(Decimal("0.000000000001"))
                    ):
                        raise PurchasingError(
                            422,
                            "stock_precision",
                            "Quantity must convert exactly to supported stock increments",
                        )
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
                        "unit_uid": UUID(item["purchase_unit_uid"]),
                        "description": line.description
                        or item["purchase_description"]
                        or item["name"],
                        "net_total": format(amount, "f"),
                        "snapshot": {
                            "item_name": item["name"],
                            "item_code": item["code"],
                            "kind": item["kind"],
                            "item_version": item["version"],
                            "unit_name": unit["name"],
                            "unit_code": unit["code"],
                            "unit_version": unit["version"],
                            "stock_unit_uid": stock_unit["uid"],
                            "stock_unit_name": stock_unit["name"],
                            "stock_increment": stock_unit["rounding_increment"],
                            "purchase_factor": unit["factor"],
                            "stock_factor": stock_unit["factor"],
                            "stock_quantity": format(stock_quantity.normalize(), "f"),
                        },
                    }
                )
            total = sum((Decimal(line["net_total"]) for line in lines), Decimal(0)).quantize(
                quantum
            )
        values = data.model_dump(exclude={"lines"})
        values.update(
            supplier_name=supplier["name"],
            company_name=company["name"],
            currency_code=currency["code"],
            net_total=format(total, "f"),
            snapshot={
                "supplier_version": supplier["version"],
                "company_version": company["version"],
                "currency_version": currency["version"],
                "minor_units": currency["minor_units"],
                "rounding": currency["rounding"],
            },
        )
        return values, lines

    def save(self, payload, *, request_uid=None, uid=None, expected_version=None):
        self.require("purchasing.write")
        data = OrderInput.model_validate(payload)
        creating = uid is None
        if creating and not request_uid:
            raise PurchasingError(422, "request_required", "A request identifier is required")
        uid = UUID(str(request_uid if creating else uid))
        if not creating:
            row = self.get(uid)
            if row["version"] != expected_version:
                raise PurchasingError(409, "conflict", "Order changed; reload and review")
            if row["state"] != "draft":
                raise PurchasingError(409, "locked", "Only a draft purchase order can be edited")
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
                    bill_uid=None,
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
        self.require("purchasing.write")
        uid = UUID(str(uid))
        row = self.get(uid)
        if row["version"] != expected_version:
            raise PurchasingError(409, "conflict", "Order changed; reload and review")
        transitions = {
            "rfq": ({"draft"}, "rfq"),
            "confirm": ({"draft", "rfq"}, "confirmed"),
            "cancel": ({"draft", "rfq", "confirmed"}, "cancelled"),
            "reopen": ({"cancelled", "rfq"}, "draft"),
            "close": ({"confirmed"}, "closed"),
        }
        if action not in transitions:
            raise PurchasingError(404, "not_found", "Unknown Purchasing action")
        allowed, target = transitions[action]
        if row["state"] not in allowed:
            raise PurchasingError(
                409, "invalid_state", "This action is not available in the current state"
            )
        if (row["bill_uid"] or row["receipts"]) and action in {"cancel", "reopen"}:
            raise PurchasingError(
                409, "downstream_records", "Related records must be resolved before cancellation"
            )
        values = {}
        steps = []
        if action in {"rfq", "confirm"}:
            if not row["lines"]:
                raise PurchasingError(
                    422, "empty_order", "Add at least one line before quoting or confirming"
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
        if action == "close":
            self.require("purchasing.manage")
            steps = self.received_plan(row)
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

    def guard(self, row, expected, values=None):
        if row["version"] != expected:
            raise PurchasingError(409, "conflict", "Order changed; reload and review")
        return GuardedStatement(
            update(Order)
            .where(
                Order.uid == UUID(row["uid"]),
                Order.version == expected,
                Order.state == row["state"],
            )
            .values(
                **(values or {}),
                version=expected + 1,
                updated_at=datetime.now(timezone.utc),
                updated_by_uid=self.actor_uid,
            )
            .returning(Order.uid),
            expect_rows=1,
            label="purchase_order_version",
        )

    def line(self, uid, line_uid, expected):
        self.require("purchasing.manage")
        row = self.get(uid)
        if row["state"] != "confirmed" or row["version"] != expected or row["bill_uid"]:
            raise PurchasingError(
                409, "receipt_state", "Select the current confirmed, unbilled purchase order"
            )
        line = next((line for line in row["lines"] if line["uid"] == str(line_uid)), None)
        if line is None:
            raise PurchasingError(422, "line", "Select a line from this purchase order")
        receipt = next((r for r in row["receipts"] if r["line_uid"] == line["uid"]), None)
        return row, line, receipt

    def same_source(self, owner):
        if str(owner.store.data_source_uid) != str(self.store.data_source_uid):
            raise PurchasingError(
                503,
                "integration_source",
                "Atomic integration requires the same governed DataSource",
            )

    def accept(self, uid, line_uid, payload):
        data = AcceptInput.model_validate(payload)
        row, line, receipt = self.line(uid, line_uid, data.expected_version)
        if line["snapshot"]["kind"] != "service" or receipt:
            raise PurchasingError(
                409, "acceptance", "Only an unclaimed service line can be accepted"
            )
        now = datetime.now(timezone.utc)
        self.transact(
            [
                self.guard(row, data.expected_version),
                insert(Receipt).values(
                    uid=data.request_uid,
                    order_uid=UUID(row["uid"]),
                    line_uid=UUID(line["uid"]),
                    kind="service",
                    state="accepted",
                    movement_uid=None,
                    reason=data.reason,
                    created_at=now,
                    updated_at=now,
                    actor_uid=self.actor_uid,
                ),
                self.audit(
                    UUID(row["uid"]), "accept-service", data.expected_version + 1, ["receipts"]
                ),
            ]
        )
        return self.get(uid)

    def revoke(self, uid, line_uid, payload):
        from .schemas import RevokeInput

        data = RevokeInput.model_validate(payload)
        row, line, receipt = self.line(uid, line_uid, data.expected_version)
        if not receipt or receipt["kind"] != "service" or receipt["state"] != "accepted":
            raise PurchasingError(
                409, "acceptance", "Only an accepted, unbilled service can be revoked"
            )
        self.transact(
            [
                self.guard(row, data.expected_version),
                update(Receipt)
                .where(Receipt.uid == UUID(receipt["uid"]))
                .values(
                    state="revoked",
                    reason=data.reason,
                    updated_at=datetime.now(timezone.utc),
                    actor_uid=self.actor_uid,
                ),
                self.audit(
                    UUID(row["uid"]), "revoke-service", data.expected_version + 1, ["receipts"]
                ),
            ]
        )
        return self.get(uid)

    def receipt(self, uid, line_uid, payload):
        data = ReceiptInput.model_validate(payload)
        row, line, receipt = self.line(uid, line_uid, data.expected_version)
        if line["snapshot"]["kind"] != "product" or receipt:
            raise PurchasingError(
                409, "receipt", "Only an unclaimed physical product line can create a receipt"
            )
        inventory = self.dependencies.inventory()
        self.same_source(inventory)
        move_uid, plan = inventory.plan_purchase_receipt(
            row, line, data.model_dump(exclude={"expected_version"})
        )
        now = datetime.now(timezone.utc)
        self.transact(
            [
                self.guard(row, data.expected_version),
                *plan,
                insert(Receipt).values(
                    uid=data.request_uid,
                    order_uid=UUID(row["uid"]),
                    line_uid=UUID(line["uid"]),
                    kind="product",
                    state="linked",
                    movement_uid=move_uid,
                    reason="Full purchase-line physical receipt",
                    created_at=now,
                    updated_at=now,
                    actor_uid=self.actor_uid,
                ),
                self.audit(UUID(row["uid"]), "receipt", data.expected_version + 1, ["receipts"]),
            ]
        )
        return self.get(uid)

    def fulfillment(self, uid):
        row = self.get(uid)
        items = []
        inventory = None
        for line in row["lines"]:
            receipt = next((r for r in row["receipts"] if r["line_uid"] == line["uid"]), None)
            received, state, movement = False, "not_received", None
            if receipt and receipt["kind"] == "service":
                state, received = receipt["state"], receipt["state"] == "accepted"
            elif receipt:
                inventory = inventory or self.dependencies.inventory()
                movement = inventory.get_movement(receipt["movement_uid"])
                state = "returned" if movement["reversal_uid"] else movement["state"]
                received = state == "done"
            items.append(
                {
                    "line_uid": line["uid"],
                    "received": received,
                    "state": state,
                    "receipt": receipt,
                    "movement": movement,
                }
            )
        return {"items": items, "all_received": bool(items) and all(x["received"] for x in items)}

    def received_plan(self, row):
        status = self.fulfillment(row["uid"])
        if not status["all_received"]:
            raise PurchasingError(
                409, "not_received", "Every line must be fully received and unreturned"
            )
        moves = [x["movement"] for x in status["items"] if x["movement"]]
        if not moves:
            return []
        inventory = self.dependencies.inventory()
        self.same_source(inventory)
        return inventory.plan_received_guard(moves)

    def bill(self, uid, payload):
        self.require("purchasing.manage")
        data = BillInput.model_validate(payload)
        row = self.get(uid)
        if (
            row["state"] not in {"confirmed", "closed"}
            or row["bill_uid"]
            or row["version"] != data.expected_version
        ):
            raise PurchasingError(
                409, "bill_state", "Choose the current confirmed or closed order without a bill"
            )
        receipts = self.received_plan(row)
        finance = self.dependencies.finance()
        self.same_source(finance)
        bill_uid, plan = finance.plan_from_purchase(
            row, data.model_dump(exclude={"expected_version"})
        )
        self.transact(
            [
                self.guard(row, data.expected_version, {"bill_uid": bill_uid}),
                *receipts,
                *plan,
                self.audit(
                    UUID(row["uid"]), "vendor-bill", data.expected_version + 1, ["bill_uid"]
                ),
            ]
        )
        return self.get(uid)
