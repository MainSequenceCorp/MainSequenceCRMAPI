"""Exact full-batch manufacturing with owner-authored atomic Inventory plans."""

from datetime import datetime, timezone
from decimal import Decimal, localcontext
from fractions import Fraction
from functools import wraps
from uuid import UUID, uuid4

from sqlalchemy import delete, func, insert, select, update

from mainsequence.client.exceptions import BadRequestError
from metatables import MetaTableTransactionGuardError
from metatables.compiled_sql.v1 import GuardedStatement
from src.erp.collections import read_page
from src.erp.module_access import require_module

from .errors import ManufacturingError
from .metatables import RESOURCES, AuditEvent, Bom, BomLine, Production, WorkStep
from .schemas import BomInput, ProductionCreate, StepFinish, StepStart


def key(uid):
    return UUID(str(uid))


def now():
    return datetime.now(timezone.utc)


def exact(fn):
    @wraps(fn)
    def call(*args, **kwargs):
        with localcontext() as ctx:
            ctx.prec = 100
            return fn(*args, **kwargs)

    return call


class Service:
    def __init__(self, store, actor_uid, capabilities, dependencies):
        self.store, self.actor_uid, self.capabilities, self.dependencies = (
            store,
            key(actor_uid),
            set(capabilities),
            dependencies,
        )

    def require(self, cap):
        require_module("manufacturing")
        if cap not in self.capabilities:
            raise ManufacturingError(
                403, "forbidden", "Manufacturing access does not permit this operation"
            )

    def created(self):
        return dict(
            version=1,
            created_at=now(),
            updated_at=now(),
            created_by_uid=self.actor_uid,
            updated_by_uid=self.actor_uid,
        )

    def get(self, resource, uid):
        self.require("manufacturing.read")
        model = RESOURCES.get(resource)
        if model is None:
            raise ManufacturingError(404, "not_found", "Unknown Manufacturing resource")
        rows = self.store.read(select(model.__table__).where(model.uid == key(uid)).limit(1))
        if not rows:
            raise ManufacturingError(404, "not_found", "Manufacturing record not found")
        row = rows[0]
        if resource == "boms":
            row["components"] = self.store.read(
                select(BomLine.__table__)
                .where(BomLine.bom_uid == key(uid))
                .order_by(BomLine.position)
                .limit(8)
            )
        else:
            row["steps"] = self.store.read(
                select(WorkStep.__table__)
                .where(WorkStep.production_uid == key(uid))
                .order_by(WorkStep.position)
                .limit(20)
            )
        return row

    def collection(self, resource, *, page_index=0, page_size=25, search="", state=None):
        self.require("manufacturing.read")
        model = RESOURCES.get(resource)
        if model is None:
            raise ManufacturingError(404, "not_found", "Unknown Manufacturing resource")
        terms = []
        if search:
            terms.append(func.lower(model.name).contains(search.lower(), autoescape=True))
        if state:
            terms.append(model.state == state)
        return read_page(
            self.store,
            model.__table__,
            terms,
            (model.created_at.desc(), model.uid),
            page_index=page_index,
            page_size=page_size,
        )

    def guard(self, model, row, expected, values=None):
        if row["version"] != expected:
            raise ManufacturingError(409, "conflict", "Record changed; reload and review")
        return GuardedStatement(
            update(model)
            .where(
                model.uid == key(row["uid"]), model.version == expected, model.state == row["state"]
            )
            .values(
                **(values or {}),
                version=expected + 1,
                updated_at=now(),
                updated_by_uid=self.actor_uid,
            )
            .returning(model.uid),
            expect_rows=1,
            label="manufacturing_version",
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
        if len(steps) > 32:
            raise ManufacturingError(
                422, "batch_limit", "The batch exceeds supported atomic operation limits"
            )
        try:
            return self.store.write(steps)
        except MetaTableTransactionGuardError as exc:
            raise ManufacturingError(
                409, "conflict", "Record or stock changed; reload and review"
            ) from exc
        except BadRequestError as exc:
            detail = (getattr(exc, "payload", {}) or {}).get("detail", {})
            if isinstance(detail, dict) and detail.get("code") == "compiled_sql_database_error":
                raise ManufacturingError(
                    409,
                    "constraint_conflict",
                    "Reference or request already exists; inspect saved records",
                ) from exc
            raise

    @exact
    def valid_quantity(self, quantity, increment):
        value = Decimal(quantity)
        ticks = value / Decimal(increment)
        if (
            value <= 0
            or ticks != ticks.to_integral_value()
            or not 1 <= ticks <= 10**12
            or value != value.quantize(Decimal("0.000000000001"))
        ):
            raise ManufacturingError(
                422,
                "quantity_precision",
                "Use a positive quantity matching the stock increment and supported limit",
            )
        return format(value.normalize(), "f")

    def product(self, uid):
        item = self.dependencies.get("catalog", "items", uid)
        if item["kind"] != "product":
            raise ManufacturingError(
                422, "physical_product", "Manufacturing requires physical products, not services"
            )
        unit = self.dependencies.get("catalog", "units", item["unit_uid"])
        self.dependencies.get("catalog", "unit-groups", unit["group_uid"])
        self.dependencies.get("catalog", "categories", item["category_uid"])
        return dict(
            item_uid=item["uid"],
            item_name=item["name"],
            item_code=item["code"],
            unit_uid=unit["uid"],
            unit_name=unit["name"],
            increment=unit["rounding_increment"],
            item_version=item["version"],
            unit_version=unit["version"],
        )

    def prepare_bom(self, data, uid):
        ids = [data.item_uid, *[c.item_uid for c in data.components]]
        if len(set(ids)) != len(ids):
            raise ManufacturingError(
                422,
                "components",
                "Each component must be unique and different from the finished product",
            )
        output = self.product(data.item_uid)
        self.valid_quantity(data.quantity, output["increment"])
        lines = []
        for position, component in enumerate(data.components, 1):
            snapshot = self.product(component.item_uid)
            self.valid_quantity(component.quantity, snapshot["increment"])
            lines.append(
                dict(
                    uid=uuid4(),
                    bom_uid=uid,
                    position=position,
                    item_uid=component.item_uid,
                    quantity=component.quantity,
                    snapshot=snapshot,
                )
            )
        return dict(
            name=data.name,
            item_uid=data.item_uid,
            quantity=data.quantity,
            operations=data.operations,
            snapshot=output,
        ), lines

    def bom(self, payload, *, request_uid=None, uid=None, expected_version=None):
        self.require("manufacturing.configure")
        data = BomInput.model_validate(payload)
        target = key(uid or request_uid)
        old = self.get("boms", uid) if uid else None
        if old and old["state"] != "draft":
            raise ManufacturingError(409, "locked", "Only draft bills of materials can be edited")
        values, lines = self.prepare_bom(data, target)
        if old:
            steps = [
                self.guard(Bom, old, expected_version, values),
                delete(BomLine).where(BomLine.bom_uid == target),
            ]
            version = expected_version + 1
        else:
            steps = [insert(Bom).values(uid=target, state="draft", **values, **self.created())]
            version = 1
        self.transact(
            [
                *steps,
                insert(BomLine).values(lines),
                self.audit("boms", target, "update" if old else "create", version, values),
            ]
        )
        return self.get("boms", target)

    def bom_action(self, uid, action, expected):
        self.require("manufacturing.configure")
        row = self.get("boms", uid)
        if action == "activate" and row["state"] == "draft":
            data = BomInput.model_validate(
                {k: row[k] for k in ["name", "item_uid", "quantity", "operations"]}
                | {
                    "components": [
                        {k: c[k] for k in ["item_uid", "quantity"]} for c in row["components"]
                    ]
                }
            )
            values, lines = self.prepare_bom(data, key(uid))
            values["state"] = "active"
            for old, new in zip(row["components"], lines):
                new["uid"] = key(old["uid"])
            steps = [
                delete(BomLine).where(BomLine.bom_uid == key(uid)),
                insert(BomLine).values(lines),
            ]
        elif action == "archive" and row["state"] in {"draft", "active"}:
            values = {"state": "archived"}
            steps = []
        else:
            raise ManufacturingError(
                409, "state", "This recipe action is unavailable in its current state"
            )
        self.transact(
            [
                self.guard(Bom, row, expected, values),
                *steps,
                self.audit("boms", uid, action, expected + 1, values),
            ]
        )
        return self.get("boms", uid)

    def inventory(self):
        owner = self.dependencies.inventory
        if str(owner.store.data_source_uid) != str(self.store.data_source_uid):
            raise ManufacturingError(
                503,
                "integration_source",
                "Production requires the same governed DataSource as Inventory",
            )
        return owner

    @exact
    def production(self, payload):
        self.require("manufacturing.write")
        data = ProductionCreate.model_validate(payload)
        bom = self.get("boms", data.bom_uid)
        if bom["state"] != "active" or bom["version"] != data.expected_bom_version:
            raise ManufacturingError(
                409, "bom_changed", "Choose the current active bill of materials"
            )
        company = self.dependencies.get("base", "operating-companies", data.operating_company_uid)
        inv = self.inventory()
        locations = [
            self.dependencies.get("inventory", "locations", x)
            for x in [data.source_uid, data.destination_uid, data.production_location_uid]
        ]
        if [x["usage"] for x in locations] != ["internal", "internal", "production"] or any(
            x["operating_company_uid"] != str(data.operating_company_uid) for x in locations
        ):
            raise ManufacturingError(
                422,
                "locations",
                "Choose two internal and one production location in the selected company",
            )
        scaled = []
        for index, line in enumerate(
            [
                *bom["components"],
                {
                    "item_uid": bom["item_uid"],
                    "quantity": bom["quantity"],
                    "snapshot": bom["snapshot"],
                },
            ]
        ):
            snapshot = self.product(line["item_uid"])
            stock = inv.stock_policy(data.operating_company_uid, line["item_uid"])
            if (
                stock["unit_uid"] != snapshot["unit_uid"]
                or Decimal(stock["increment"]) != Decimal(snapshot["increment"])
                or stock["currency_uid"] != company["currency_uid"]
            ):
                raise ManufacturingError(
                    422, "stock_policy", "Stock policy must match current unit and company currency"
                )
            amount = Decimal(line["quantity"]) * Decimal(data.quantity) / Decimal(bom["quantity"])
            if Fraction(amount) != Fraction(line["quantity"]) * Fraction(data.quantity) / Fraction(
                bom["quantity"]
            ):
                raise ManufacturingError(
                    422,
                    "quantity_precision",
                    "Scaled component quantity must be exactly representable",
                )
            quantity = self.valid_quantity(format(amount, "f"), stock["increment"])
            scaled.append(
                {
                    "stock_item_uid": stock["uid"],
                    "quantity": quantity,
                    **snapshot,
                    "unit_cost": stock["unit_cost"],
                }
            )
        snapshot = {
            "bom_uid": bom["uid"],
            "bom_name": bom["name"],
            "bom_version": bom["version"],
            "company_name": company["name"],
            "currency_code": stock["snapshot"]["currency_code"],
            "output": scaled[-1],
            "components": scaled[:-1],
            "source_name": locations[0]["name"],
            "destination_name": locations[1]["name"],
            "production_location_name": locations[2]["name"],
        }
        values = data.model_dump(exclude={"request_uid", "expected_bom_version"})
        # A no-change version fence prevents recipe archival between selection and order creation.
        bom_fence = GuardedStatement(
            update(Bom)
            .where(
                Bom.uid == data.bom_uid,
                Bom.version == data.expected_bom_version,
                Bom.state == "active",
            )
            .values(updated_at=Bom.updated_at)
            .returning(Bom.uid),
            expect_rows=1,
            label="active_bom",
        )
        self.transact(
            [
                bom_fence,
                insert(Production).values(
                    uid=data.request_uid,
                    **values,
                    state="draft",
                    snapshot=snapshot,
                    movement_uids=[],
                    finance_posted=False,
                    **self.created(),
                ),
                insert(WorkStep).values(
                    [
                        dict(
                            uid=uuid4(),
                            production_uid=data.request_uid,
                            position=i,
                            name=name,
                            state="pending",
                            minutes=0,
                            evidence="",
                            started_at=None,
                            finished_at=None,
                            **self.created(),
                        )
                        for i, name in enumerate(bom["operations"], 1)
                    ]
                ),
                self.audit("orders", data.request_uid, "create", 1, values),
            ]
        )
        return self.get("orders", data.request_uid)

    def transition(self, uid, action, expected):
        self.require("manufacturing.manage")
        row = self.get("orders", uid)
        values = {}
        steps = []
        if row["version"] != expected:
            raise ManufacturingError(409, "conflict", "Production changed; reload and review")
        if action == "reserve" and row["state"] == "draft":
            bom = self.get("boms", row["bom_uid"])
            if bom["state"] != "active" or bom["version"] != row["snapshot"]["bom_version"]:
                raise ManufacturingError(
                    409,
                    "bom_changed",
                    "The selected recipe was archived or changed; create a reviewed replacement order",
                )
            steps.append(
                GuardedStatement(
                    update(Bom)
                    .where(
                        Bom.uid == key(bom["uid"]),
                        Bom.version == bom["version"],
                        Bom.state == "active",
                    )
                    .values(updated_at=Bom.updated_at)
                    .returning(Bom.uid),
                    expect_rows=1,
                    label="active_bom",
                )
            )
            payload = {
                k: row[k]
                for k in [
                    "name",
                    "operating_company_uid",
                    "source_uid",
                    "destination_uid",
                    "production_location_uid",
                ]
            }
            payload.update(
                order_uid=row["uid"],
                output={k: row["snapshot"]["output"][k] for k in ["stock_item_uid", "quantity"]},
                components=[
                    {k: c[k] for k in ["stock_item_uid", "quantity"]}
                    for c in row["snapshot"]["components"]
                ],
            )
            uids, plan = self.inventory().plan_prepare_production(payload)
            steps += plan
            values = {"state": "ready", "movement_uids": uids}
        elif action == "cancel" and row["state"] in {"draft", "ready"}:
            if row["state"] == "ready":
                steps = self.inventory().plan_transition_production(
                    uid, row["movement_uids"], "cancel"
                )
            steps.append(
                update(WorkStep)
                .where(WorkStep.production_uid == key(uid))
                .values(
                    state="cancelled",
                    version=WorkStep.version + 1,
                    updated_at=now(),
                    updated_by_uid=self.actor_uid,
                )
            )
            values = {"state": "cancelled"}
        elif action == "complete" and row["state"] == "progress":
            if any(step["state"] != "done" for step in row["steps"]):
                raise ManufacturingError(409, "work_pending", "Complete every work operation first")
            steps = self.inventory().plan_transition_production(
                uid, row["movement_uids"], "complete"
            )
            values = {"state": "done"}
        elif action == "finance" and row["state"] == "done" and not row["finance_posted"]:
            steps = self.inventory().plan_finance_production(uid, row["movement_uids"])
            values = {"finance_posted": True}
        else:
            raise ManufacturingError(
                409, "state", "This production action is unavailable in its current state"
            )
        self.transact(
            [
                self.guard(Production, row, expected, values),
                *steps,
                self.audit("orders", uid, action, expected + 1, values),
            ]
        )
        return self.get("orders", uid)

    def step(self, uid, step_uid, action, payload):
        self.require("manufacturing.manage")
        data = (StepStart if action == "start" else StepFinish).model_validate(payload)
        row = self.get("orders", uid)
        if row["state"] not in {"ready", "progress"}:
            raise ManufacturingError(409, "state", "Reserve stock before starting work")
        step = next((x for x in row["steps"] if x["uid"] == str(step_uid)), None)
        if step is None:
            raise ManufacturingError(404, "not_found", "Work step not found in this order")
        if any(x["state"] != "done" for x in row["steps"] if x["position"] < step["position"]):
            raise ManufacturingError(409, "work_sequence", "Finish the preceding operations first")
        if action == "start" and step["state"] == "pending":
            values = {"state": "progress", "started_at": now()}
        elif action == "finish" and step["state"] == "progress":
            values = {
                "state": "done",
                "finished_at": now(),
                "minutes": data.minutes,
                "evidence": data.evidence,
            }
        else:
            raise ManufacturingError(409, "work_state", "This work step action is unavailable")
        self.transact(
            [
                self.guard(Production, row, data.expected_version, {"state": "progress"}),
                self.guard(WorkStep, step, data.expected_step_version, values),
                self.audit("orders", uid, "work_" + action, data.expected_version + 1, ["steps"]),
            ]
        )
        return self.get("orders", uid)

    def valuation(self, uid):
        row = self.get("orders", uid)
        return (
            self.inventory().production_valuation(uid, row["movement_uids"])
            if row["movement_uids"]
            else {"items": []}
        )

    def history(self, resource, uid):
        self.require("manufacturing.manage")
        self.get(resource, uid)
        return {
            "items": self.store.read(
                select(AuditEvent.__table__)
                .where(AuditEvent.resource == resource, AuditEvent.record_uid == key(uid))
                .order_by(AuditEvent.occurred_at.desc())
                .limit(100)
            )
        }
