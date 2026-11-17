"""Exact, version-fenced Finance aggregates, balanced postings and allocations."""

from datetime import datetime, timezone
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext
from functools import wraps
from uuid import UUID, uuid4

from sqlalchemy import delete, func, insert, or_, select, update

from mainsequence.client.exceptions import BadRequestError
from metatables import MetaTableTransactionGuardError
from metatables.compiled_sql.v1 import GuardedStatement

from .errors import FinanceError
from .metatables import RESOURCES, Allocation, AuditEvent, Invoice, InvoiceLine, Payment, Posting
from .schemas import AllocationInput, FromSalesInput, InvoiceInput, PaymentInput


def exact(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with localcontext() as context:
            context.prec = 80
            return function(*args, **kwargs)

    return wrapped


def now():
    return datetime.now(timezone.utc)


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
            raise FinanceError(403, "forbidden", "Finance access does not permit this operation")

    def model(self, resource):
        if resource not in RESOURCES:
            raise FinanceError(404, "not_found", "Unknown Finance collection")
        return RESOURCES[resource]

    @exact
    def get(self, resource, uid):
        self.require("finance.read")
        model = self.model(resource)
        uid = UUID(str(uid))
        rows = self.store.read(select(model.__table__).where(model.uid == uid).limit(1))
        if not rows:
            raise FinanceError(404, "not_found", "Finance record not found")
        row = rows[0]
        row["remaining"] = (
            "0"
            if row["state"] == "void"
            else str(Decimal(row["total"]) - Decimal(row["allocated"]))
        )
        row["payment_status"] = (
            "void"
            if row["state"] == "void"
            else "paid"
            if row["state"] == "posted" and Decimal(row["remaining"]) == 0
            else "partial"
            if Decimal(row["allocated"]) > 0
            else "unpaid"
        )
        if resource == "invoices":
            row["lines"] = self.store.read(
                select(InvoiceLine.__table__)
                .where(InvoiceLine.invoice_uid == uid)
                .order_by(InvoiceLine.position)
                .limit(100)
            )
        allocations = self.allocation_collection(resource, uid)
        row["allocations"] = allocations["items"]
        row["allocations_page_info"] = allocations["pageInfo"]
        row["postings"] = self.store.read(
            select(Posting.__table__)
            .where(Posting.resource == resource, Posting.record_uid == uid)
            .order_by(Posting.occurred_at, Posting.account_role)
            .limit(20)
        )
        return row

    def allocation_collection(self, resource, uid, *, page_index=0, page_size=25):
        self.require("finance.read")
        model = self.model(resource)
        uid = UUID(str(uid))
        if not self.store.read(select(model.uid).where(model.uid == uid).limit(1)):
            raise FinanceError(404, "not_found", "Finance record not found")
        link = Allocation.invoice_uid if resource == "invoices" else Allocation.payment_uid
        total = int(
            self.store.read(
                select(func.count().label("count")).select_from(Allocation).where(link == uid)
            )[0]["count"]
        )
        items = self.store.read(
            select(
                Allocation.__table__,
                Invoice.name.label("invoice_reference"),
                Payment.name.label("payment_reference"),
            )
            .join(Invoice, Invoice.uid == Allocation.invoice_uid)
            .join(Payment, Payment.uid == Allocation.payment_uid)
            .where(link == uid)
            .order_by(Allocation.created_at.desc(), Allocation.uid)
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

    def collection(self, resource, *, page_index=0, page_size=25, search="", state=None):
        self.require("finance.read")
        model = self.model(resource)
        terms = []
        if search:
            terms.append(
                or_(
                    func.lower(model.name).contains(search.lower(), autoescape=True),
                    func.lower(model.party_name).contains(search.lower(), autoescape=True),
                )
            )
        if state:
            terms.append(model.state == state)
        total = int(
            self.store.read(select(func.count().label("count")).select_from(model).where(*terms))[
                0
            ]["count"]
        )
        items = self.store.read(
            select(model.__table__)
            .where(*terms)
            .order_by(model.created_at.desc(), model.uid)
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
            raise FinanceError(
                409, "conflict", "Financial record changed; reload and review before retrying"
            ) from exc
        except BadRequestError as exc:
            detail = (getattr(exc, "payload", {}) or {}).get("detail", {})
            if isinstance(detail, dict) and detail.get("code") == "compiled_sql_database_error":
                raise FinanceError(
                    409,
                    "constraint_conflict",
                    "This reference, source or request already exists; check the saved record",
                ) from exc
            raise

    def audit(self, resource, uid, action, version, fields):
        return insert(AuditEvent).values(
            uid=uuid4(),
            resource=resource,
            record_uid=UUID(str(uid)),
            action=action,
            version=version,
            actor_uid=self.actor_uid,
            occurred_at=now(),
            fields=sorted(fields),
        )

    def guard(self, resource, row, version, values):
        model = self.model(resource)
        return GuardedStatement(
            update(model)
            .where(
                model.uid == UUID(row["uid"]), model.version == version, model.state == row["state"]
            )
            .values(**values, version=version + 1, updated_at=now(), updated_by_uid=self.actor_uid)
            .returning(model.uid),
            expect_rows=1,
            label="finance_version",
        )

    def references(self, data):
        party = self.dependencies.get("parties", data.party_uid)
        company = self.dependencies.get("operating-companies", data.operating_company_uid)
        self.dependencies.get("parties", company["party_uid"])
        currency = self.dependencies.get("currencies", data.currency_uid)
        if str(company["currency_uid"]) != str(data.currency_uid):
            raise FinanceError(
                422,
                "company_currency",
                "This Finance release requires the operating company currency",
            )
        snapshot = {
            "party_version": party["version"],
            "company_version": company["version"],
            "currency_version": currency["version"],
            "minor_units": currency["minor_units"],
            "rounding": currency["rounding"],
        }
        return {
            "party_name": party["name"],
            "company_name": company["name"],
            "currency_code": currency["code"],
            "snapshot": snapshot,
        }

    def quantize(self, value, snapshot, *, strict=False):
        number = Decimal(value)
        quantum = Decimal(1).scaleb(-snapshot["minor_units"])
        rounded = number.quantize(
            quantum,
            rounding=ROUND_HALF_EVEN if snapshot["rounding"] == "half_even" else ROUND_HALF_UP,
        )
        if strict and number != rounded:
            raise FinanceError(422, "precision", "Amount exceeds the selected currency precision")
        return rounded

    @exact
    def prepare(self, resource, payload, uid):
        data = (InvoiceInput if resource == "invoices" else PaymentInput).model_validate(payload)
        refs = self.references(data)
        values = {**data.model_dump(exclude={"lines", "amount"}), **refs}
        lines = []
        if resource == "invoices":
            for position, line in enumerate(data.lines, 1):
                net = self.quantize(
                    Decimal(line.quantity)
                    * Decimal(line.unit_price)
                    * (1 - Decimal(line.discount) / 100),
                    refs["snapshot"],
                )
                tax = self.quantize(net * Decimal(line.tax_rate) / 100, refs["snapshot"])
                lines.append(
                    {
                        "uid": uuid4(),
                        "invoice_uid": uid,
                        "position": position,
                        **line.model_dump(),
                        "net_total": str(net),
                        "tax_total": str(tax),
                        "total": str(net + tax),
                        "source": {},
                    }
                )
            net = sum((Decimal(line["net_total"]) for line in lines), Decimal(0))
            tax = sum((Decimal(line["tax_total"]) for line in lines), Decimal(0))
            values.update(net_total=str(net), tax_total=str(tax), total=str(net + tax))
        else:
            values["total"] = str(self.quantize(data.amount, refs["snapshot"], strict=True))
        return values, lines

    def draft_payload(self, resource, row):
        schema = InvoiceInput if resource == "invoices" else PaymentInput
        result = {key: row[key] for key in schema.model_fields if key not in {"lines", "amount"}}
        if resource == "invoices":
            result["lines"] = [
                {
                    key: line[key]
                    for key in ("description", "quantity", "unit_price", "discount", "tax_rate")
                }
                for line in row["lines"]
            ]
        else:
            result["amount"] = row["total"]
        return result

    @exact
    def save(self, resource, payload, *, uid=None, expected_version=None, request_uid=None):
        self.require("finance.write")
        model = self.model(resource)
        uid = UUID(str(uid)) if uid else None
        old = self.get(resource, uid) if uid else None
        if old and (old["state"] != "draft" or old["version"] != expected_version):
            raise FinanceError(
                409, "conflict", "Only the current draft can be edited; reload and review"
            )
        target = uid or UUID(str(request_uid))
        values, lines = self.prepare(resource, payload, target)
        if old and resource == "invoices" and old["source_order_uid"]:
            before = self.draft_payload(resource, old)
            after = InvoiceInput.model_validate(payload).model_dump(mode="json")
            for key in ("kind", "party_uid", "operating_company_uid", "currency_uid"):
                if str(before[key]) != str(after[key]):
                    raise FinanceError(
                        422, "source_terms", "Source Sales identities and currency cannot change"
                    )
            if len(old["lines"]) != len(lines):
                raise FinanceError(422, "source_terms", "Source Sales lines cannot change")
            for previous, line in zip(old["lines"], lines):
                if any(
                    previous[k] != line[k]
                    for k in ("description", "quantity", "unit_price", "discount", "net_total")
                ):
                    raise FinanceError(
                        422, "source_terms", "Source Sales quantities and prices cannot change"
                    )
                line["source"] = previous["source"]
        if old:
            steps = [self.guard(resource, old, expected_version, values)]
            if resource == "invoices":
                steps.append(delete(InvoiceLine).where(InvoiceLine.invoice_uid == target))
            version = expected_version + 1
        else:
            values.update(
                uid=target,
                state="draft",
                allocated="0",
                version=1,
                created_at=now(),
                updated_at=now(),
                posted_at=None,
                void_reason="",
                created_by_uid=self.actor_uid,
                updated_by_uid=self.actor_uid,
            )
            if resource == "invoices":
                values.update(source_order_uid=None, source_order_name=None)
            steps = [insert(model).values(**values)]
            version = 1
        if lines:
            steps.append(insert(InvoiceLine).values(lines))
        steps.append(
            self.audit(resource, target, "update" if old else "create", version, values.keys())
        )
        self.transact(steps)
        return self.get(resource, target)

    @exact
    def posting_steps(self, resource, row, phase):
        total = Decimal(row["total"])
        customer = row["kind"] == "customer"
        if resource == "invoices":
            net, tax = Decimal(row["net_total"]), Decimal(row["tax_total"])
            entries = (
                [("receivable", total), ("income", -net), ("tax_payable", -tax)]
                if customer
                else [("expense", net), ("tax_recoverable", tax), ("payable", -total)]
            )
        else:
            entries = (
                [("bank", total), ("receivable", -total)]
                if customer
                else [("payable", total), ("bank", -total)]
            )
        if sum(value for _, value in entries) != 0:
            raise FinanceError(422, "unbalanced", "Posting entries do not balance")
        return [
            insert(Posting).values(
                [
                    {
                        "uid": uuid4(),
                        "resource": resource,
                        "record_uid": UUID(row["uid"]),
                        "operating_company_uid": UUID(row["operating_company_uid"]),
                        "currency_uid": UUID(row["currency_uid"]),
                        "phase": phase,
                        "account_role": role,
                        "amount": str(-amount if phase == "void" else amount),
                        "occurred_at": now(),
                    }
                    for role, amount in entries
                    if amount != 0
                ]
            )
        ]

    @exact
    def transition(self, resource, uid, action, expected_version, reason=""):
        self.require("finance.post")
        row = self.get(resource, uid)
        if row["version"] != expected_version:
            raise FinanceError(409, "conflict", "Financial record changed; reload and review")
        steps = []
        if action == "post":
            if row["state"] != "draft":
                raise FinanceError(409, "invalid_state", "Only drafts can be posted")
            if Decimal(row["total"]) <= 0 or resource == "invoices" and not row["lines"]:
                raise FinanceError(
                    422, "empty_document", "Posting requires a positive amount and invoice lines"
                )
            if str(row["document_date"])[:10] > now().date().isoformat():
                raise FinanceError(422, "future_date", "Future-dated records cannot post yet")
            refs = self.references(
                (InvoiceInput if resource == "invoices" else PaymentInput).model_validate(
                    self.draft_payload(resource, row)
                )
            )
            if any(refs["snapshot"][k] != row["snapshot"][k] for k in ("minor_units", "rounding")):
                raise FinanceError(
                    409,
                    "currency_changed",
                    "Currency precision changed; review and save the draft before posting",
                )
            steps = self.posting_steps(resource, row, "post")
            values = {"state": "posted", "posted_at": now()}
        elif action == "void":
            if not reason.strip():
                raise FinanceError(
                    422, "reason_required", "Provide a reason for cancellation or reversal"
                )
            if row["state"] == "void":
                raise FinanceError(409, "invalid_state", "This record is already void")
            if Decimal(row["allocated"]) != 0:
                raise FinanceError(
                    409, "allocated", "Reverse active payment allocations before voiding"
                )
            if row["state"] == "posted":
                steps = self.posting_steps(resource, row, "void")
            values = {"state": "void", "void_reason": reason}
        else:
            raise FinanceError(422, "invalid_action", "Unknown Finance action")
        self.transact(
            [
                self.guard(resource, row, expected_version, values),
                *steps,
                self.audit(resource, uid, action, expected_version + 1, values.keys()),
            ]
        )
        return self.get(resource, uid)

    @exact
    def allocate(self, payload):
        self.require("finance.post")
        data = AllocationInput.model_validate(payload)
        invoice = self.get("invoices", data.invoice_uid)
        payment = self.get("payments", data.payment_uid)
        if invoice["state"] != "posted" or payment["state"] != "posted":
            raise FinanceError(409, "invalid_state", "Allocation requires posted documents")
        if any(
            invoice[k] != payment[k]
            for k in ("kind", "party_uid", "operating_company_uid", "currency_uid")
        ):
            raise FinanceError(
                422, "mismatch", "Invoice and payment must match kind, party, company and currency"
            )
        amount = self.quantize(data.amount, invoice["snapshot"], strict=True)
        if amount > Decimal(invoice["remaining"]) or amount > Decimal(payment["remaining"]):
            raise FinanceError(
                409,
                "insufficient_balance",
                "Allocation exceeds the remaining invoice or payment amount",
            )
        self.transact(
            [
                self.guard(
                    "invoices",
                    invoice,
                    data.expected_invoice_version,
                    {"allocated": str(Decimal(invoice["allocated"]) + amount)},
                ),
                self.guard(
                    "payments",
                    payment,
                    data.expected_payment_version,
                    {"allocated": str(Decimal(payment["allocated"]) + amount)},
                ),
                insert(Allocation).values(
                    uid=data.request_uid,
                    invoice_uid=data.invoice_uid,
                    payment_uid=data.payment_uid,
                    amount=str(amount),
                    state="active",
                    created_at=now(),
                    created_by_uid=self.actor_uid,
                    reversed_at=None,
                ),
                self.audit(
                    "invoices",
                    data.invoice_uid,
                    "allocate",
                    data.expected_invoice_version + 1,
                    ["allocated"],
                ),
                self.audit(
                    "payments",
                    data.payment_uid,
                    "allocate",
                    data.expected_payment_version + 1,
                    ["allocated"],
                ),
            ]
        )
        return {
            "invoice": self.get("invoices", data.invoice_uid),
            "payment": self.get("payments", data.payment_uid),
            "allocation_uid": str(data.request_uid),
        }

    @exact
    def reverse_allocation(self, uid, expected_invoice_version, expected_payment_version):
        self.require("finance.post")
        uid = UUID(str(uid))
        rows = self.store.read(select(Allocation.__table__).where(Allocation.uid == uid).limit(1))
        if not rows:
            raise FinanceError(404, "not_found", "Allocation not found")
        allocation = rows[0]
        if allocation["state"] != "active":
            raise FinanceError(409, "invalid_state", "Allocation is already reversed")
        invoice = self.get("invoices", allocation["invoice_uid"])
        payment = self.get("payments", allocation["payment_uid"])
        amount = Decimal(allocation["amount"])
        if (
            invoice["state"] != "posted"
            or payment["state"] != "posted"
            or amount > min(Decimal(invoice["allocated"]), Decimal(payment["allocated"]))
        ):
            raise FinanceError(409, "allocation_state", "Allocation balances require review")
        self.transact(
            [
                self.guard(
                    "invoices",
                    invoice,
                    expected_invoice_version,
                    {"allocated": str(Decimal(invoice["allocated"]) - amount)},
                ),
                self.guard(
                    "payments",
                    payment,
                    expected_payment_version,
                    {"allocated": str(Decimal(payment["allocated"]) - amount)},
                ),
                GuardedStatement(
                    update(Allocation)
                    .where(Allocation.uid == uid, Allocation.state == "active")
                    .values(state="reversed", reversed_at=now())
                    .returning(Allocation.uid),
                    expect_rows=1,
                    label="allocation_active",
                ),
                self.audit(
                    "invoices",
                    invoice["uid"],
                    "unallocate",
                    expected_invoice_version + 1,
                    ["allocated"],
                ),
                self.audit(
                    "payments",
                    payment["uid"],
                    "unallocate",
                    expected_payment_version + 1,
                    ["allocated"],
                ),
            ]
        )
        return {
            "invoice": self.get("invoices", invoice["uid"]),
            "payment": self.get("payments", payment["uid"]),
            "allocation_uid": str(uid),
        }

    @exact
    def from_sales(self, payload):
        self.require("finance.write")
        data = FromSalesInput.model_validate(payload)
        sales = self.dependencies.sales()
        if str(sales.store.data_source_uid) != str(self.store.data_source_uid):
            raise FinanceError(
                503,
                "integration_source",
                "Atomic Sales integration requires the same governed DataSource",
            )
        order = sales.get(data.order_uid)
        if order["state"] != "confirmed" or order["version"] != data.expected_order_version:
            raise FinanceError(409, "source_changed", "Select the current confirmed Sales order")
        invoice = {
            "name": data.name,
            "kind": "customer",
            "party_uid": order["customer_uid"],
            "operating_company_uid": order["operating_company_uid"],
            "currency_uid": order["currency_uid"],
            "document_date": data.document_date,
            "due_date": data.due_date,
            "notes": order["notes"],
            "lines": [
                {
                    **{
                        key: line[key]
                        for key in ("description", "quantity", "unit_price", "discount")
                    },
                    "tax_rate": data.tax_rate,
                }
                for line in order["lines"]
            ],
        }
        values, lines = self.prepare("invoices", invoice, data.request_uid)
        for source, line in zip(order["lines"], lines):
            if Decimal(source["net_total"]) != Decimal(line["net_total"]):
                raise FinanceError(
                    409,
                    "source_precision",
                    "Current currency precision would change the confirmed order amount",
                )
            line["source"] = {
                "order_uid": order["uid"],
                "line_uid": source["uid"],
                "item_uid": source["item_uid"],
                "unit_uid": source["unit_uid"],
                "item_name": source["snapshot"]["item_name"],
            }
        values.update(
            uid=data.request_uid,
            state="draft",
            allocated="0",
            version=1,
            created_at=now(),
            updated_at=now(),
            posted_at=None,
            void_reason="",
            created_by_uid=self.actor_uid,
            updated_by_uid=self.actor_uid,
            source_order_uid=data.order_uid,
            source_order_name=order["name"],
        )
        plan = sales.plan_attach(
            data.order_uid, data.expected_order_version, "finance", data.request_uid
        )
        self.transact(
            [
                *plan,
                insert(Invoice).values(**values),
                insert(InvoiceLine).values(lines),
                self.audit("invoices", data.request_uid, "from-sales", 1, values.keys()),
            ]
        )
        return self.get("invoices", data.request_uid)
