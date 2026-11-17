"""Exact stock movements and owner-authorized cross-module transaction plans."""

from datetime import datetime, timezone
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext
from functools import wraps
from uuid import UUID, uuid4

from sqlalchemy import func, insert, or_, select, update

from mainsequence.client.exceptions import BadRequestError
from metatables import MetaTableTransactionGuardError
from metatables.compiled_sql.v1 import GuardedStatement

from .errors import InventoryError
from .metatables import RESOURCES, AuditEvent, Balance, Entry, Location, Move, StockItem
from .schemas import (
    FromSales,
    LocationCreate,
    LocationUpdate,
    MovementCreate,
    ReturnInput,
    StockItemCreate,
)

MAX_TICKS = 10**12


def key(value):
    return UUID(str(value))


def now():
    return datetime.now(timezone.utc)


def exact(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with localcontext() as ctx:
            ctx.prec = 80
            return fn(*args, **kwargs)

    return wrapped


class Service:
    def __init__(self, store, actor_uid, capabilities, dependencies):
        self.store, self.actor_uid, self.capabilities, self.dependencies = (
            store,
            key(actor_uid),
            set(capabilities),
            dependencies,
        )

    def require(self, cap):
        if cap not in self.capabilities:
            raise InventoryError(
                403, "forbidden", "Inventory access does not permit this operation"
            )

    def raw(self, resource, uid):
        self.require("inventory.read")
        model = RESOURCES.get(resource)
        if model is None:
            raise InventoryError(404, "not_found", "Unknown Inventory resource")
        rows = self.store.read(select(model.__table__).where(model.uid == key(uid)).limit(1))
        if not rows:
            raise InventoryError(404, "not_found", "Inventory record not found")
        return rows[0]

    @exact
    def get(self, resource, uid):
        row = self.raw(resource, uid)
        if resource == "balances":
            stock = self.raw("stock-items", row["stock_item_uid"])
            location = self.raw("locations", row["location_uid"])
            row.update(
                name=stock["name"],
                location_name=location["name"],
                unit_name=stock["snapshot"]["unit_name"],
                currency_code=stock["snapshot"]["currency_code"],
            )
            for name, ticks in [
                ("on_hand", row["on_hand_ticks"]),
                ("reserved", row["reserved_ticks"]),
                ("available", row["on_hand_ticks"] - row["reserved_ticks"]),
            ]:
                row[name] = str(Decimal(ticks) * Decimal(stock["increment"]))
            row["standard_cost_estimate"] = self.value(Decimal(row["on_hand"]), stock)
        if resource == "movements":
            row["entries"] = self.store.read(
                select(Entry.__table__)
                .where(Entry.move_uid == key(uid))
                .order_by(Entry.location_uid)
            )
            for entry in row["entries"]:
                entry["quantity"] = str(
                    Decimal(entry["quantity_ticks"]) * Decimal(row["snapshot"]["increment"])
                )
        return row

    def count(self, model, *terms):
        return int(
            self.store.read(select(func.count().label("count")).select_from(model).where(*terms))[
                0
            ]["count"]
        )

    def collection(
        self,
        resource,
        *,
        page_index=0,
        page_size=25,
        search="",
        state=None,
        include_archived=False,
        operating_company_uid=None,
        stock_item_uid=None,
    ):
        self.require("inventory.read")
        model = RESOURCES.get(resource)
        if model is None:
            raise InventoryError(404, "not_found", "Unknown Inventory resource")
        terms = []
        if hasattr(model, "archived_at") and not include_archived:
            terms.append(model.archived_at.is_(None))
        if state and resource == "movements":
            terms.append(Move.state == state)
        if operating_company_uid:
            if resource in {"locations", "stock-items"}:
                terms.append(model.operating_company_uid == key(operating_company_uid))
            else:
                terms.append(
                    model.stock_item_uid.in_(
                        select(StockItem.uid).where(
                            StockItem.operating_company_uid == key(operating_company_uid)
                        )
                    )
                )
        if stock_item_uid and resource in {"movements", "balances"}:
            terms.append(model.stock_item_uid == key(stock_item_uid))
        if search:
            if resource == "balances":
                terms.append(
                    Balance.stock_item_uid.in_(
                        select(StockItem.uid).where(
                            func.lower(StockItem.name).contains(search.lower(), autoescape=True)
                        )
                    )
                )
            else:
                terms.append(func.lower(model.name).contains(search.lower(), autoescape=True))
        total = self.count(model, *terms)
        rows = self.store.read(
            select(model.uid)
            .where(*terms)
            .order_by(model.created_at.desc(), model.uid)
            .offset(page_index * page_size)
            .limit(page_size),
            max_rows=page_size,
        )
        return {
            "items": [self.get(resource, row["uid"]) for row in rows],
            "pageInfo": {
                "pageIndex": page_index,
                "pageSize": page_size,
                "totalItems": total,
                "hasNextPage": (page_index + 1) * page_size < total,
                "hasPreviousPage": page_index > 0,
            },
        }

    def history(self, resource, uid, *, page_index=0, page_size=25):
        self.require("inventory.manage")
        self.raw(resource, uid)
        terms = [AuditEvent.resource == resource, AuditEvent.record_uid == key(uid)]
        total = self.count(AuditEvent, *terms)
        return {
            "items": self.store.read(
                select(AuditEvent.__table__)
                .where(*terms)
                .order_by(AuditEvent.occurred_at.desc(), AuditEvent.uid)
                .offset(page_index * page_size)
                .limit(page_size),
                max_rows=page_size,
            ),
            "pageInfo": {
                "pageIndex": page_index,
                "pageSize": page_size,
                "totalItems": total,
                "hasNextPage": (page_index + 1) * page_size < total,
                "hasPreviousPage": page_index > 0,
            },
        }

    def created(self):
        return dict(
            version=1,
            created_at=now(),
            updated_at=now(),
            created_by_uid=self.actor_uid,
            updated_by_uid=self.actor_uid,
        )

    def guard(self, model, row, values, expected=None):
        terms = [
            model.uid == key(row["uid"]),
            model.version == (row["version"] if expected is None else expected),
        ]
        if hasattr(model, "state"):
            terms.append(model.state == row["state"])
        return GuardedStatement(
            update(model)
            .where(*terms)
            .values(
                **values,
                version=row["version"] + 1,
                updated_at=now(),
                updated_by_uid=self.actor_uid,
            )
            .returning(model.uid),
            expect_rows=1,
            label="inventory_version",
        )

    def audit(self, resource, uid, action, version, fields):
        return insert(AuditEvent).values(
            uid=uuid4(),
            resource=resource,
            record_uid=key(uid),
            action=action,
            version=version,
            actor_uid=self.actor_uid,
            occurred_at=now(),
            fields=sorted(fields),
        )

    def transact(self, steps):
        try:
            self.store.write(steps)
        except MetaTableTransactionGuardError as error:
            raise InventoryError(
                409, "conflict", "Stock changed; reload and review before trying again"
            ) from error
        except BadRequestError as error:
            if any(term in str(error).lower() for term in ["unique", "constraint", "duplicate"]):
                raise InventoryError(
                    409,
                    "conflict",
                    "Stock identity or balance changed; inspect saved records before retrying",
                ) from error
            raise

    def active(self, resource, uid):
        row = self.raw(resource, uid)
        if row.get("archived_at"):
            raise InventoryError(
                409, "archived", "Restore this stock configuration before using it"
            )
        return row

    def version(self, row, expected):
        if row["version"] != expected:
            raise InventoryError(409, "conflict", "Record changed; reload and review")

    def location(self, payload, uid=None):
        self.require("inventory.configure")
        data = (LocationUpdate if uid else LocationCreate).model_validate(payload)
        if uid:
            row = self.active("locations", uid)
            self.version(row, data.expected_version)
            values = data.model_dump(exclude={"expected_version"})
            steps = [self.guard(Location, row, values)]
            version = row["version"] + 1
        else:
            self.dependencies.get("base", "operating-companies", data.operating_company_uid)
            uid = data.request_uid
            values = data.model_dump(exclude={"request_uid"})
            steps = [insert(Location).values(uid=uid, **values, archived_at=None, **self.created())]
            version = 1
        self.transact(
            [
                *steps,
                self.audit(
                    "locations", uid, "rename" if version > 1 else "create", version, values
                ),
            ]
        )
        return self.get("locations", uid)

    def stock_item(self, payload):
        self.require("inventory.configure")
        data = StockItemCreate.model_validate(payload)
        item = self.dependencies.get("catalog", "items", data.item_uid)
        if item["kind"] != "product":
            raise InventoryError(
                422, "product_required", "Stock policies require physical Catalog products"
            )
        unit = self.dependencies.get("catalog", "units", item["unit_uid"])
        self.dependencies.get("catalog", "unit-groups", unit["group_uid"])
        self.dependencies.get("catalog", "categories", item["category_uid"])
        company = self.dependencies.get("base", "operating-companies", data.operating_company_uid)
        currency = self.dependencies.get("base", "currencies", company["currency_uid"])
        values = dict(
            item_uid=data.item_uid,
            operating_company_uid=data.operating_company_uid,
            name=item["name"],
            currency_uid=key(currency["uid"]),
            unit_uid=key(unit["uid"]),
            increment=unit["rounding_increment"],
            unit_cost=data.unit_cost,
            snapshot={
                "company_name": company["name"],
                "company_version": company["version"],
                "currency_code": currency["code"],
                "currency_version": currency["version"],
                "minor_units": currency["minor_units"],
                "rounding": currency["rounding"],
                "item_code": item["code"],
                "item_version": item["version"],
                "unit_name": unit["name"],
                "unit_version": unit["version"],
            },
        )
        self.transact(
            [
                insert(StockItem).values(
                    uid=data.request_uid, **values, archived_at=None, **self.created()
                ),
                self.audit("stock-items", data.request_uid, "create", 1, values),
            ]
        )
        return self.get("stock-items", data.request_uid)

    def archive(self, resource, uid, expected, *, restore=False):
        self.require("inventory.configure")
        if resource not in {"locations", "stock-items"}:
            raise InventoryError(
                422, "resource", "Only stock policies and locations can be archived"
            )
        row = self.raw(resource, uid)
        self.version(row, expected)
        model = RESOURCES[resource]
        if bool(row["archived_at"]) == restore:
            pass
        else:
            raise InventoryError(409, "invalid_state", "Archive state changed; reload the record")
        if not restore:
            b = (
                Balance.location_uid == key(uid)
                if resource == "locations"
                else Balance.stock_item_uid == key(uid)
            )
            m = (
                or_(Move.source_uid == key(uid), Move.destination_uid == key(uid))
                if resource == "locations"
                else Move.stock_item_uid == key(uid)
            )
            if self.count(
                Balance, b, or_(Balance.on_hand_ticks > 0, Balance.reserved_ticks > 0)
            ) or self.count(Move, m, Move.state.in_(["draft", "ready"])):
                raise InventoryError(
                    409, "in_use", "Configuration has stock or unfinished movements"
                )
        self.transact(
            [
                self.guard(model, row, {"archived_at": None if restore else now()}),
                self.audit(
                    resource,
                    uid,
                    "restore" if restore else "archive",
                    expected + 1,
                    ["archived_at"],
                ),
            ]
        )
        return self.get(resource, uid)

    @exact
    def ticks(self, quantity, stock):
        number = Decimal(quantity) / Decimal(stock["increment"])
        if number != number.to_integral_value() or not 0 < number <= MAX_TICKS:
            raise InventoryError(
                422,
                "quantity_increment",
                "Quantity must be an exact positive multiple of the stock increment within the supported limit",
            )
        return int(number)

    @exact
    def value(self, quantity, stock):
        return format(
            (Decimal(quantity) * Decimal(stock["unit_cost"])).quantize(
                Decimal(1).scaleb(-stock["snapshot"]["minor_units"]),
                rounding=ROUND_HALF_EVEN
                if stock["snapshot"]["rounding"] == "half_even"
                else ROUND_HALF_UP,
            ),
            "f",
        )

    def balance(self, stock_uid, location_uid):
        rows = self.store.read(
            select(Balance.__table__)
            .where(
                Balance.stock_item_uid == key(stock_uid), Balance.location_uid == key(location_uid)
            )
            .limit(1)
        )
        return rows[0] if rows else None

    @exact
    def plan_movement(self, payload):
        self.require("inventory.write")
        data = MovementCreate.model_validate(payload)
        stock = self.active("stock-items", data.stock_item_uid)
        source = self.active("locations", data.source_uid)
        dest = self.active("locations", data.destination_uid)
        if source["uid"] == dest["uid"] or any(
            row["operating_company_uid"] != stock["operating_company_uid"] for row in [source, dest]
        ):
            raise InventoryError(
                422, "locations", "Choose different locations in the stock item company"
            )
        kinds = {
            ("supplier", "internal"): "receipt",
            ("internal", "customer"): "delivery",
            ("internal", "internal"): "transfer",
            ("adjustment", "internal"): "adjustment_in",
            ("production", "internal"): "production_in",
            ("internal", "production"): "production_out",
            ("internal", "adjustment"): "adjustment_out",
        }
        kind = kinds.get((source["usage"], dest["usage"]))
        if not kind:
            raise InventoryError(
                422,
                "location_usage",
                "This location pair does not define a supported stock operation",
            )
        if kind.startswith("adjustment") and not data.reason:
            raise InventoryError(422, "reason_required", "Adjustments require an explanation")
        ticks = self.ticks(data.quantity, stock)
        signed = (1 if dest["usage"] == "internal" else 0) - (
            1 if source["usage"] == "internal" else 0
        )
        snapshot = {
            **stock["snapshot"],
            "item_name": stock["name"],
            "unit_uid": stock["unit_uid"],
            "increment": stock["increment"],
            "unit_cost": stock["unit_cost"],
            "operating_company_uid": stock["operating_company_uid"],
            "currency_uid": stock["currency_uid"],
            "source_name": source["name"],
            "destination_name": dest["name"],
            "source_usage": source["usage"],
            "destination_usage": dest["usage"],
        }
        values = {
            **data.model_dump(exclude={"request_uid"}),
            "uid": data.request_uid,
            "quantity_ticks": ticks,
            "kind": kind,
            "state": "draft",
            "snapshot": snapshot,
            "net_value": self.value(Decimal(data.quantity) * signed, stock),
            "sales_order_uid": None,
            "manufacturing_order_uid": None,
            "sales_line_uid": None,
            "reversal_uid": None,
            "reverses_uid": None,
            "finance_posted": False,
            "completed_at": None,
            **self.created(),
        }
        steps = [
            self.guard(StockItem, stock, {}),
            self.guard(Location, source, {}),
            self.guard(Location, dest, {}),
        ]
        for loc in [source, dest]:
            if loc["usage"] == "internal" and not self.balance(stock["uid"], loc["uid"]):
                steps.append(
                    insert(Balance).values(
                        uid=uuid4(),
                        stock_item_uid=key(stock["uid"]),
                        location_uid=key(loc["uid"]),
                        on_hand_ticks=0,
                        reserved_ticks=0,
                        **self.created(),
                    )
                )
        return values, steps

    def movement(self, payload):
        values, steps = self.plan_movement(payload)
        if values["kind"].startswith("production_"):
            raise InventoryError(
                422,
                "coordinated_production",
                "Create production movements through a Manufacturing order",
            )
        uid = values["uid"]
        self.transact(
            [
                *steps,
                insert(Move).values(**values),
                self.audit("movements", uid, "create", 1, values),
            ]
        )
        return self.get("movements", uid)

    def balance_change(self, row, on_hand, reserved):
        if not 0 <= reserved <= on_hand <= MAX_TICKS:
            raise InventoryError(
                409,
                "insufficient_stock",
                "Not enough unreserved stock, or the destination exceeds its supported balance",
            )
        return self.guard(Balance, row, {"on_hand_ticks": on_hand, "reserved_ticks": reserved})

    @exact
    def completion_steps(self, row, *, reserved):
        result = []
        ticks = row["quantity_ticks"]
        unit_value = abs(Decimal(row["quantity"]) * Decimal(row["snapshot"]["unit_cost"]))
        snap = row["snapshot"]
        value = unit_value.quantize(
            Decimal(1).scaleb(-snap["minor_units"]),
            rounding=ROUND_HALF_EVEN if snap["rounding"] == "half_even" else ROUND_HALF_UP,
        )
        for side, sign in [("source", -1), ("destination", 1)]:
            if snap[side + "_usage"] != "internal":
                continue
            balance = self.balance(row["stock_item_uid"], row[side + "_uid"])
            if not balance:
                raise InventoryError(
                    409,
                    "balance_missing",
                    "Stock balance is unavailable; inspect migration and saved movement",
                )
            result.append(
                self.balance_change(
                    balance,
                    balance["on_hand_ticks"] + sign * ticks,
                    balance["reserved_ticks"] - (ticks if sign < 0 and reserved else 0),
                )
            )
            result.append(
                insert(Entry).values(
                    uid=uuid4(),
                    move_uid=key(row["uid"]),
                    stock_item_uid=key(row["stock_item_uid"]),
                    location_uid=key(row[side + "_uid"]),
                    quantity_ticks=sign * ticks,
                    value=str(value * sign),
                    occurred_at=now(),
                )
            )
        return result

    def transition(self, uid, action, expected):
        self.require("inventory.manage")
        row = self.raw("movements", uid)
        self.require_standalone(row)
        self.version(row, expected)
        steps = []
        if action == "prepare" and row["state"] == "draft":
            self.active("stock-items", row["stock_item_uid"])
            self.active("locations", row["source_uid"])
            self.active("locations", row["destination_uid"])
            if row["snapshot"]["source_usage"] == "internal":
                balance = self.balance(row["stock_item_uid"], row["source_uid"])
                steps.append(
                    self.balance_change(
                        balance,
                        balance["on_hand_ticks"],
                        balance["reserved_ticks"] + row["quantity_ticks"],
                    )
                )
            state = "ready"
        elif action == "complete" and row["state"] == "ready":
            steps = self.completion_steps(row, reserved=True)
            state = "done"
        elif action == "cancel" and row["state"] in {"draft", "ready"}:
            if row["state"] == "ready" and row["snapshot"]["source_usage"] == "internal":
                balance = self.balance(row["stock_item_uid"], row["source_uid"])
                steps.append(
                    self.balance_change(
                        balance,
                        balance["on_hand_ticks"],
                        balance["reserved_ticks"] - row["quantity_ticks"],
                    )
                )
            state = "cancelled"
        else:
            raise InventoryError(
                409, "invalid_state", "This movement action is unavailable in its current state"
            )
        values = {"state": state, **({"completed_at": now()} if state == "done" else {})}
        self.transact(
            [
                self.guard(Move, row, values),
                *steps,
                self.audit("movements", uid, action, expected + 1, values),
            ]
        )
        return self.get("movements", uid)

    def same_source(self, owner):
        if owner.store.data_source_uid != self.store.data_source_uid:
            raise InventoryError(
                409, "source_mismatch", "Cross-module plans require the same verified source"
            )

    def from_sales(self, payload):
        self.require("inventory.manage")
        data = FromSales.model_validate(payload)
        sales = self.dependencies.sales()
        self.same_source(sales)
        order = sales.get(data.order_uid)
        if order["state"] != "confirmed" or order["version"] != data.expected_order_version:
            raise InventoryError(409, "order_changed", "Choose the current confirmed Sales order")
        line = next((line for line in order["lines"] if line["uid"] == str(data.line_uid)), None)
        if line is None:
            raise InventoryError(422, "line", "Choose a line from this order")
        stock = self.active("stock-items", data.stock_item_uid)
        if (
            stock["item_uid"] != line["item_uid"]
            or stock["unit_uid"] != line["unit_uid"]
            or stock["snapshot"]["unit_version"] != line["snapshot"]["unit_version"]
            or stock["operating_company_uid"] != order["operating_company_uid"]
            or line["snapshot"]["kind"] != "product"
        ):
            raise InventoryError(
                422,
                "sales_stock_mismatch",
                "Choose the matching company product and stock unit for this Sales line",
            )
        values, steps = self.plan_movement(
            {
                **data.model_dump(exclude={"order_uid", "line_uid", "expected_order_version"}),
                "quantity": line["quantity"],
                "reason": "Confirmed Sales line fulfillment",
            }
        )
        if values["kind"] != "delivery":
            raise InventoryError(
                422,
                "delivery",
                "Sales fulfillment requires an internal source and customer destination",
            )
        values.update(sales_order_uid=data.order_uid, sales_line_uid=data.line_uid)
        self.transact(
            [
                *steps,
                *sales.plan_attach(
                    data.order_uid, data.expected_order_version, "inventory", data.request_uid
                ),
                insert(Move).values(**values),
                self.audit("movements", data.request_uid, "sales_delivery", 1, values),
            ]
        )
        return self.get("movements", data.request_uid)

    def post_finance(self, uid, expected):
        self.require("inventory.manage")
        row = self.raw("movements", uid)
        self.require_standalone(row)
        self.version(row, expected)
        if (
            row["state"] != "done"
            or row["finance_posted"]
            or row["reversal_uid"]
            or row["reverses_uid"]
            or row["snapshot"]["source_usage"] == row["snapshot"]["destination_usage"]
        ):
            raise InventoryError(
                409,
                "valuation_state",
                "Only unreversed completed external movements can be handed to Finance once",
            )
        finance = self.dependencies.finance()
        self.same_source(finance)
        steps = finance.plan_inventory_valuation(
            uid,
            row["snapshot"]["operating_company_uid"],
            row["snapshot"]["currency_uid"],
            row["net_value"],
        )
        self.transact(
            [
                self.guard(Move, row, {"finance_posted": True}),
                *steps,
                self.audit("movements", uid, "finance_post", expected + 1, ["finance_posted"]),
            ]
        )
        return self.get("movements", uid)

    @exact
    def reverse(self, uid, payload):
        self.require("inventory.manage")
        data = ReturnInput.model_validate(payload)
        row = self.raw("movements", uid)
        self.require_standalone(row)
        self.version(row, data.expected_version)
        if row["state"] != "done" or row["reversal_uid"] or row["reverses_uid"]:
            raise InventoryError(
                409, "return_state", "Only an original completed movement can be returned once"
            )
        snapshot = {
            **row["snapshot"],
            "source_name": row["snapshot"]["destination_name"],
            "destination_name": row["snapshot"]["source_name"],
            "source_usage": row["snapshot"]["destination_usage"],
            "destination_usage": row["snapshot"]["source_usage"],
        }
        values = {
            key_: value for key_, value in row.items() if key_ in Move.__table__.columns.keys()
        }
        values.update(
            uid=data.request_uid,
            name=("Return: " + row["name"])[:200],
            source_uid=row["destination_uid"],
            destination_uid=row["source_uid"],
            kind="return",
            reason=data.reason,
            snapshot=snapshot,
            net_value=str(-Decimal(row["net_value"])),
            sales_order_uid=None,
            sales_line_uid=None,
            reversal_uid=None,
            reverses_uid=key(uid),
            completed_at=now(),
            **self.created(),
        )
        # SQL values use typed identities; read responses serialize UUIDs as text.
        for field in ["stock_item_uid", "source_uid", "destination_uid"]:
            values[field] = key(values[field])
        stock = self.active("stock-items", row["stock_item_uid"])
        source = self.active("locations", row["source_uid"])
        destination = self.active("locations", row["destination_uid"])
        steps = [
            self.guard(StockItem, stock, {}),
            self.guard(Location, source, {}),
            self.guard(Location, destination, {}),
            self.guard(Move, row, {"reversal_uid": data.request_uid}),
            insert(Move).values(**values),
            *self.completion_steps(values, reserved=False),
        ]
        if row["finance_posted"]:
            finance = self.dependencies.finance()
            self.same_source(finance)
            steps += finance.plan_inventory_valuation(
                data.request_uid,
                snapshot["operating_company_uid"],
                snapshot["currency_uid"],
                values["net_value"],
            )
        self.transact(
            [
                *steps,
                self.audit("movements", uid, "reverse", row["version"] + 1, ["reversal_uid"]),
                self.audit("movements", data.request_uid, "return", 1, values),
            ]
        )
        return self.get("movements", data.request_uid)

    def finance_entries(self, uid):
        row = self.raw("movements", uid)
        if not row["finance_posted"]:
            return {"items": []}
        finance = self.dependencies.finance()
        self.same_source(finance)
        return finance.inventory_valuation(uid)

    def plan_purchase_receipt(self, order, line, payload):
        """Complete owner-authored plan; caller joins its own guarded unique line claim."""
        self.require("inventory.manage")
        stock = self.active("stock-items", payload["stock_item_uid"])
        if (
            order["state"] != "confirmed"
            or line["snapshot"]["kind"] != "product"
            or stock["item_uid"] != line["item_uid"]
            or stock["unit_uid"] != line["snapshot"]["stock_unit_uid"]
            or stock["increment"] != line["snapshot"]["stock_increment"]
            or stock["operating_company_uid"] != order["operating_company_uid"]
        ):
            raise InventoryError(
                422,
                "purchase_stock_mismatch",
                "Choose the matching company, product and stock unit for this purchase line",
            )
        values, steps = self.plan_movement(
            {
                **payload,
                "quantity": line["snapshot"]["stock_quantity"],
                "reason": "Confirmed full purchase-line receipt",
            }
        )
        if values["kind"] != "receipt":
            raise InventoryError(
                422,
                "receipt_locations",
                "Purchasing requires a supplier source and internal destination",
            )
        values["snapshot"].update(
            purchase_order_uid=str(order["uid"]),
            purchase_order_name=order["name"],
            purchase_line_uid=str(line["uid"]),
        )
        uid = values["uid"]
        return uid, [
            *steps,
            insert(Move).values(**values),
            self.audit("movements", uid, "purchase_receipt", 1, values),
        ]

    def plan_received_guard(self, moves):
        """Fence all received movements together, within the SDK transaction statement limit."""
        self.require("inventory.manage")
        from sqlalchemy import and_, or_

        if not moves or len(moves) > 100:
            raise InventoryError(
                422, "receipts", "Provide one through one hundred receipt references"
            )
        current = [self.get("movements", row["uid"]) for row in moves]
        if len({row["uid"] for row in current}) != len(current) or any(
            row["state"] != "done"
            or row["reversal_uid"]
            or row["reverses_uid"]
            or row["kind"] != "receipt"
            or row["version"] != original["version"]
            for row, original in zip(current, moves)
        ):
            raise InventoryError(
                409, "receipt_changed", "Receipts must be current, completed and unreturned"
            )
        return [
            GuardedStatement(
                update(Move)
                .where(
                    or_(
                        *(
                            and_(Move.uid == key(row["uid"]), Move.version == row["version"])
                            for row in current
                        )
                    ),
                    Move.state == "done",
                    Move.reversal_uid.is_(None),
                    Move.reverses_uid.is_(None),
                )
                .values(version=Move.version + 1, updated_at=now(), updated_by_uid=self.actor_uid)
                .returning(Move.uid),
                expect_rows=len(current),
                label="received_movements",
            )
        ]

    def stock_policy(self, company_uid, item_uid):
        """Public read contract for the unique active company/product policy."""
        self.require("inventory.read")
        rows = self.store.read(
            select(StockItem.uid)
            .where(
                StockItem.operating_company_uid == key(company_uid),
                StockItem.item_uid == key(item_uid),
            )
            .limit(1)
        )
        if not rows:
            raise InventoryError(
                422, "stock_policy", "Configure a stock item for every company product first"
            )
        return self.active("stock-items", rows[0]["uid"])

    def plan_prepare_production(self, payload):
        from .production import ProductionPlans

        return ProductionPlans(self).prepare(payload)

    def plan_transition_production(self, *args):
        from .production import ProductionPlans

        return ProductionPlans(self).transition(*args)

    def plan_finance_production(self, *args):
        from .production import ProductionPlans

        return ProductionPlans(self).finance(*args)

    def production_valuation(self, *args):
        from .production import ProductionPlans

        return ProductionPlans(self).valuation(*args)

    def require_standalone(self, row):
        if row.get("manufacturing_order_uid"):
            raise InventoryError(
                409,
                "coordinated_production",
                "Manage this complete stock batch through its Manufacturing order",
            )
