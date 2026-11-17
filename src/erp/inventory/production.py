"""Inventory-owned complete production plans; no Manufacturing model imports."""

from uuid import uuid4, uuid5

from sqlalchemy import and_, insert, or_, select, update

from metatables.compiled_sql.v1 import GuardedStatement

from .errors import InventoryError
from .metatables import AuditEvent, Balance, Location, Move, StockItem
from .schemas import ProductionPlanInput
from .service import key, now


class ProductionPlans:
    def __init__(self, service):
        self.s = service

    def guard_many(self, model, rows, values=None):
        if not rows or len({str(row["uid"]) for row in rows}) != len(rows):
            raise InventoryError(422, "batch", "Batch references must be unique and nonempty")
        predicates = []
        for row in rows:
            terms = [model.uid == key(row["uid"]), model.version == row["version"]]
            if hasattr(model, "state"):
                terms.append(model.state == row["state"])
            if hasattr(model, "archived_at"):
                terms.append(model.archived_at.is_(None))
            predicates.append(and_(*terms))
        return GuardedStatement(
            update(model)
            .where(or_(*predicates))
            .values(
                **(values or {}),
                version=model.version + 1,
                updated_at=now(),
                updated_by_uid=self.s.actor_uid,
            )
            .returning(model.uid),
            expect_rows=len(rows),
            label="production_stock_batch",
        )

    def audits(self, moves, action):
        return insert(AuditEvent).values(
            [
                dict(
                    uid=uuid4(),
                    resource="movements",
                    record_uid=key(row["uid"]),
                    action=action,
                    version=row["version"] + 1,
                    actor_uid=self.s.actor_uid,
                    occurred_at=now(),
                    fields=["state", "production"],
                )
                for row in moves
            ]
        )

    def prepare(self, payload):
        self.s.require("inventory.manage")
        data = ProductionPlanInput.model_validate(payload)
        products = [*data.components, data.output]
        if len({p.stock_item_uid for p in products}) != len(products):
            raise InventoryError(
                422, "products", "Production components and finished output must be distinct"
            )
        policies = [self.s.active("stock-items", p.stock_item_uid) for p in products]
        locations = [
            self.s.active("locations", uid)
            for uid in [data.source_uid, data.destination_uid, data.production_location_uid]
        ]
        if any(
            row["operating_company_uid"] != str(data.operating_company_uid)
            for row in [*policies, *locations]
        ) or [x["usage"] for x in locations] != ["internal", "internal", "production"]:
            raise InventoryError(
                422,
                "production_locations",
                "Choose matching company policies, two internal locations and a virtual production location",
            )
        unique_locs = list({row["uid"]: row for row in locations}.values())
        steps = [self.guard_many(StockItem, policies), self.guard_many(Location, unique_locs)]
        moves = []
        for i, product in enumerate(products):
            output = i == len(products) - 1
            uid = uuid5(data.order_uid, str(product.stock_item_uid))
            values, _ = self.s.plan_movement(
                dict(
                    request_uid=uid,
                    name=data.name + (" output" if output else f" component {i + 1}"),
                    stock_item_uid=product.stock_item_uid,
                    source_uid=data.production_location_uid if output else data.source_uid,
                    destination_uid=data.destination_uid
                    if output
                    else data.production_location_uid,
                    quantity=product.quantity,
                    reason="Coordinated full manufacturing batch",
                )
            )
            values.update(state="ready", manufacturing_order_uid=data.order_uid)
            values["snapshot"].update(
                manufacturing_order_uid=str(data.order_uid), manufacturing_order_name=data.name
            )
            moves.append(values)
            location = data.destination_uid if output else data.source_uid
            balance = self.s.balance(product.stock_item_uid, location)
            if output:
                if not balance:
                    steps.append(
                        insert(Balance).values(
                            uid=uuid4(),
                            stock_item_uid=product.stock_item_uid,
                            location_uid=location,
                            on_hand_ticks=0,
                            reserved_ticks=0,
                            **self.s.created(),
                        )
                    )
            else:
                if not balance:
                    raise InventoryError(
                        409,
                        "insufficient_stock",
                        "All production components must have enough available stock",
                    )
                steps.append(
                    self.s.balance_change(
                        balance,
                        balance["on_hand_ticks"],
                        balance["reserved_ticks"] + values["quantity_ticks"],
                    )
                )
        steps.extend(
            [
                insert(Move).values(moves),
                self.audits([{**row, "version": 0} for row in moves], "production_reserve"),
            ]
        )
        return [str(row["uid"]) for row in moves], steps

    def moves(self, order_uid, uids):
        self.s.require("inventory.read")
        rows = self.s.store.read(
            select(Move.__table__)
            .where(Move.manufacturing_order_uid == key(order_uid))
            .order_by(Move.uid)
            .limit(10)
        )
        if (
            not 2 <= len(rows) <= 9
            or {str(uid) for uid in uids} != {row["uid"] for row in rows}
            or len(uids) != len(rows)
        ):
            raise InventoryError(
                409, "production_batch", "Use the complete owned production movement set"
            )
        return rows

    def transition(self, order_uid, uids, action):
        self.s.require("inventory.manage")
        rows = self.moves(order_uid, uids)
        if action not in {"cancel", "complete"} or any(row["state"] != "ready" for row in rows):
            raise InventoryError(
                409,
                "production_state",
                "Production stock must be fully reserved before this action",
            )
        steps = []
        for row in rows:
            if action == "complete":
                steps.extend(self.s.completion_steps(row, reserved=True))
            elif row["kind"] == "production_out":
                balance = self.s.balance(row["stock_item_uid"], row["source_uid"])
                steps.append(
                    self.s.balance_change(
                        balance,
                        balance["on_hand_ticks"],
                        balance["reserved_ticks"] - row["quantity_ticks"],
                    )
                )
        values = {"state": "done" if action == "complete" else "cancelled"}
        if action == "complete":
            values["completed_at"] = now()
        return [
            self.guard_many(Move, rows, values),
            *steps,
            self.audits(rows, "production_" + action),
        ]

    def finance(self, order_uid, uids):
        self.s.require("inventory.manage")
        rows = self.moves(order_uid, uids)
        if any(row["state"] != "done" or row["finance_posted"] for row in rows):
            raise InventoryError(
                409,
                "production_valuation",
                "Only a complete unposted production batch can be valued once",
            )
        finance = self.s.dependencies.finance()
        self.s.same_source(finance)
        steps = []
        for row in rows:
            steps.extend(
                finance.plan_inventory_valuation(
                    row["uid"],
                    row["snapshot"]["operating_company_uid"],
                    row["snapshot"]["currency_uid"],
                    row["net_value"],
                )
            )
        return [
            self.guard_many(Move, rows, {"finance_posted": True}),
            *steps,
            self.audits(rows, "production_finance"),
        ]

    def valuation(self, order_uid, uids):
        rows = self.moves(order_uid, uids)
        return {
            "items": [
                {
                    "movement_uid": row["uid"],
                    "kind": row["kind"],
                    "quantity": row["quantity"],
                    "net_value": row["net_value"],
                    "currency_code": row["snapshot"]["currency_code"],
                    "finance_posted": row["finance_posted"],
                    "entries": self.s.finance_entries(row["uid"])["items"]
                    if row["finance_posted"]
                    else [],
                }
                for row in rows
            ]
        }
