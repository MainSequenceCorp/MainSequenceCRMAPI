"""Finance-owned reconciliation, independent of file formats and provider adapters."""

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx
from sqlalchemy import and_, insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from mainsequence.client import ResourceRelease
from metatables.compiled_sql.v1 import GuardedStatement
from src.erp.module_access import require_integration
from src.erp.user_preferences.connector_registry import local_target
from src.erp.user_preferences.integrations import LOCAL_TOKEN_HEADER

from .banking_contracts import Evidence, SourceAccount, Transaction
from .errors import FinanceError
from .metatables import (
    Allocation,
    BankAccount,
    BankCounterpartyAlias,
    BankGrantFence,
    BankIntakeOperation,
    BankMovement,
    BankMovementSource,
    BankReview,
    BankSourceAccountMap,
    Invoice,
    Payment,
)
from .service import exact, now

WORKFLOW = "finance.bank-reconciliation"
FENCE_PATH = "/api/finance/v1/intake/grant-fences/"


def uid(value):
    return UUID(str(value))


def digest(value):
    encoding = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoding.encode()).hexdigest()


def amount_key(value):
    return format(Decimal(value).normalize(), "f")


def instant(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def one_guard(statement, label):
    return GuardedStatement(statement, expect_rows=1, label=label)


def stale():
    return FinanceError(
        409, "stale_review", "Bank evidence, mapping or Finance state changed. Review again."
    )


def fence_uid(scope, binding, installation, binding_generation, connection):
    return uuid5(
        NAMESPACE_URL,
        f"finance:bank:{scope}:{binding}:{installation}:{binding_generation}:{connection}",
    )


def change_fence(store, scope, command, *, guards, local):
    """Make close monotonic, including a close that arrives before its open."""
    model = BankGrantFence.__table__
    key = fence_uid(
        scope,
        command.binding,
        command.installation_uid,
        command.binding_generation,
        command.connection_uid,
    )
    state = "closed" if command.action == "close" else "open"
    new = model.c.generation < command.generation
    same = model.c.generation == command.generation
    allowed = (
        or_(new, same)
        if state == "closed"
        else or_(and_(new, model.c.state == "closed"), and_(same, model.c.state == "open"))
    )
    payload = command.model_dump(exclude={"binding", "action", "operation_uid"})
    stmt = (
        (sqlite_insert if local else pg_insert)(model)
        .values(
            uid=key,
            environment_uid=scope,
            binding_key=command.binding,
            state=state,
            **payload,
        )
        .on_conflict_do_update(
            index_elements=[model.c.uid],
            where=and_(
                allowed,
                model.c.actor_uid == command.actor_uid,
                model.c.source_account_uid == command.source_account_uid,
            ),
            set_={"state": state, "generation": command.generation},
        )
        .returning(model.c.state, model.c.generation)
    )
    rows = store.write([*guards, stmt])
    if rows:
        return rows[0]
    current = store.read(select(model).where(model.c.uid == key))
    if (
        current
        and str(current[0]["actor_uid"]) == str(command.actor_uid)
        and str(current[0]["source_account_uid"]) == str(command.source_account_uid)
    ):
        if current[0]["generation"] > command.generation or current[0]["state"] == "closed":
            return {"state": "closed", "generation": command.generation}
    raise stale()


class Connector:
    def __init__(self, binding, local):
        self.binding, self.local = binding, local

    def post(self, path, body, schema):
        try:
            release = self.binding.release_uid
            if self.local:
                target = local_target(release)
                if not target.token:
                    raise ValueError("Missing peer credential")
                with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
                    response = client.post(
                        target.origin + path, json=body, headers={LOCAL_TOKEN_HEADER: target.token}
                    )
            else:
                response = ResourceRelease.by_uid(release).request(
                    "POST",
                    path,
                    json=body,
                    timeout=10,
                    ready_timeout=10,
                    idempotent=True,
                    allow_redirects=False,
                )
            if response.status_code in {401, 403, 404, 409, 422}:
                raise stale()
            if response.status_code != 200:
                raise ValueError("Unavailable connector")
            return schema.model_validate(response.json())
        except FinanceError:
            raise
        except Exception as exc:
            raise FinanceError(
                503, "connector_unavailable", "Banking evidence is unavailable"
            ) from exc

    def source(self, actor, source_uid):
        return self.post(
            "/api/connector/v1/banking/source-accounts/verify/",
            {
                "binding": self.binding.key,
                "actor_uid": str(actor),
                "source_account_uid": str(source_uid),
            },
            SourceAccount,
        )

    def redeem(self, actor, token, purpose):
        return self.post(
            "/api/connector/v1/claims/redeem/",
            {
                "binding": self.binding.key,
                "actor_uid": str(actor),
                "claim_token": token,
                "purpose": purpose,
            },
            Evidence,
        )


class Banking:
    def __init__(self, finance, scope, *, local=False):
        self.finance, self.store = finance, finance.store
        self.actor, self.scope, self.local = finance.actor_uid, scope, local

    @property
    def company(self):
        try:
            return uid(os.environ["ERP_FINANCE_BANKING_COMPANY_UID"])
        except (KeyError, ValueError) as exc:
            raise FinanceError(
                503, "banking_unconfigured", "Configure the pilot operating company first"
            ) from exc

    def one(self, query):
        return next(iter(self.store.read(query.limit(1), max_rows=1)), None)

    def connector(self, binding_key):
        policy = require_integration(binding_key)
        binding = policy["connector_binding"]
        if binding.workflow_key != WORKFLOW:
            raise FinanceError(
                403, "wrong_workflow", "This binding does not support Finance reconciliation"
            )
        return Connector(binding, self.local)

    def account(self, account_uid):
        account = self.one(
            select(BankAccount.__table__).where(
                BankAccount.uid == uid(account_uid),
                BankAccount.environment_uid == self.scope,
                BankAccount.company_uid == self.company,
            )
        )
        if not account:
            raise FinanceError(404, "bank_account_unavailable", "Bank account is unavailable")
        return account

    def accounts(self):
        self.finance.require("finance.read")
        return self.store.read(
            select(
                BankAccount.uid,
                BankAccount.masked_label,
                BankAccount.company_uid,
                BankAccount.currency_uid,
            )
            .where(
                BankAccount.environment_uid == self.scope,
                BankAccount.company_uid == self.company,
            )
            .order_by(BankAccount.masked_label)
            .limit(100)
        )

    def mapping(self, installation, source_uid):
        row = self.one(
            select(BankSourceAccountMap.__table__).where(
                BankSourceAccountMap.environment_uid == self.scope,
                BankSourceAccountMap.installation_uid == uid(installation),
                BankSourceAccountMap.source_account_uid == uid(source_uid),
            )
        )
        if not row:
            raise FinanceError(
                409, "unmapped_account", "Approve the source-to-company account mapping first"
            )
        return row, self.account(row["bank_account_uid"])

    def save_mapping(self, command):
        self.finance.require("finance.configure")
        connector = self.connector(command.binding)
        source = connector.source(self.actor, command.source_account_uid)
        if source.company_uid != self.company or source.uid != command.source_account_uid:
            raise FinanceError(
                403, "company_scope", "This source is outside the approved operating company"
            )
        company = self.finance.dependencies.get("operating-companies", self.company)
        currency_uid = uid(company["currency_uid"])
        currency = self.finance.dependencies.get("currencies", currency_uid)
        if currency["code"] != source.currency_code:
            raise FinanceError(
                422,
                "company_currency",
                "The mapped account must use the operating-company currency",
            )
        binding = connector.binding
        previous = self.one(
            select(BankSourceAccountMap.__table__).where(
                BankSourceAccountMap.environment_uid == self.scope,
                BankSourceAccountMap.installation_uid == binding.installation_uid,
                BankSourceAccountMap.source_account_uid == source.uid,
            )
        )
        if previous:
            if (
                command.bank_account_uid is not None
                and uid(previous["bank_account_uid"]) != command.bank_account_uid
            ):
                raise FinanceError(
                    409, "mapping_conflict", "The source already has an approved canonical account"
                )
            return {
                "mapping_uid": previous["uid"],
                "bank_account_uid": previous["bank_account_uid"],
                "version": previous["version"],
            }
        if source.requires_existing_account and command.bank_account_uid is None:
            raise FinanceError(422, "confirm_account_mapping", "Choose the verified Finance bank account")
        account = (
            self.account(command.bank_account_uid)
            if command.bank_account_uid
            else self.one(
                select(BankAccount.__table__).where(
                    BankAccount.environment_uid == self.scope,
                    BankAccount.company_uid == self.company,
                    BankAccount.currency_uid == currency_uid,
                    BankAccount.fingerprint == source.account_fingerprint,
                )
            )
        )
        steps = []
        if account:
            if uid(account["currency_uid"]) != currency_uid:
                raise FinanceError(
                    422, "company_currency", "The canonical account uses a different currency"
                )
            account_uid = uid(account["uid"])
            steps.append(self.account_guard(account))
        else:
            account_uid = uuid4()
            steps.append(
                insert(BankAccount).values(
                    uid=account_uid,
                    environment_uid=self.scope,
                    company_uid=self.company,
                    currency_uid=currency_uid,
                    fingerprint=source.account_fingerprint,
                    masked_label=source.masked_label,
                    intake_version=1,
                )
            )
        mapping_uid = uuid4()
        steps.extend(
            [
                insert(BankSourceAccountMap).values(
                    uid=mapping_uid,
                    environment_uid=self.scope,
                    installation_uid=binding.installation_uid,
                    source_account_uid=source.uid,
                    bank_account_uid=account_uid,
                    version=1,
                    actor_uid=self.actor,
                    created_at=now(),
                ),
                self.finance.audit(
                    "bank-movements", mapping_uid, "map-source", 1, ["bank_account_uid"]
                ),
            ]
        )
        self.finance.transact(steps)
        return {"mapping_uid": mapping_uid, "bank_account_uid": account_uid, "version": 1}

    def validate_evidence(self, connector, evidence):
        if (
            evidence.actor_uid != self.actor
            or evidence.operating_company_uid != self.company
            or evidence.installation_uid != connector.binding.installation_uid
            or evidence.binding_generation != connector.binding.generation
            or digest(evidence.transaction.model_dump(mode="json")) != evidence.evidence_sha256
        ):
            raise stale()

    def source_rule(self, evidence):
        kind, key = evidence.identity
        return (
            BankMovementSource.environment_uid == self.scope,
            BankMovementSource.installation_uid == evidence.installation_uid,
            BankMovementSource.source_account_uid == evidence.source_account_uid,
            BankMovementSource.identity_kind == kind,
            BankMovementSource.identity_key == key,
        )

    def fence_query(self, binding, evidence):
        return select(BankGrantFence.uid).where(
            BankGrantFence.uid
            == fence_uid(
                self.scope,
                binding,
                evidence.installation_uid,
                evidence.binding_generation,
                evidence.connection_uid,
            ),
            BankGrantFence.actor_uid == self.actor,
            BankGrantFence.source_account_uid == evidence.source_account_uid,
            BankGrantFence.state == "open",
            BankGrantFence.generation == evidence.generation,
        )

    def account_guard(self, account):
        return one_guard(
            update(BankAccount)
            .where(
                BankAccount.uid == uid(account["uid"]),
                BankAccount.intake_version == account["intake_version"],
            )
            .values(intake_version=account["intake_version"] + 1)
            .returning(BankAccount.uid),
            "bank_account_version",
        )

    def candidate_rows(self, account, transaction, party_uid=None):
        refs = {
            value.upper()
            for value in (transaction.structured_reference, transaction.end_to_end_reference)
            if value
        }
        if party_uid:
            self.finance.dependencies.get("parties", party_uid)
        elif transaction.counterparty_fingerprint:
            alias = self.one(
                select(BankCounterpartyAlias.party_uid).where(
                    BankCounterpartyAlias.environment_uid == self.scope,
                    BankCounterpartyAlias.company_uid == self.company,
                    BankCounterpartyAlias.fingerprint == transaction.counterparty_fingerprint,
                )
            )
            if alias:
                party_uid = uid(alias["party_uid"])
        invoice_scope = []
        if refs:
            invoice_scope.append(Invoice.name.in_(refs))
        if party_uid:
            invoice_scope.append(Invoice.party_uid == party_uid)
        invoices = (
            self.store.read(
                select(
                    Invoice.uid,
                    Invoice.version,
                    Invoice.name,
                    Invoice.party_uid,
                    Invoice.party_name,
                    Invoice.total,
                    Invoice.allocated,
                    Invoice.currency_code,
                )
                .where(
                    Invoice.operating_company_uid == self.company,
                    Invoice.kind == "customer",
                    Invoice.currency_uid == uid(account["currency_uid"]),
                    Invoice.currency_code == transaction.currency_code,
                    Invoice.state == "posted",
                    or_(*invoice_scope),
                )
                .order_by(Invoice.due_date, Invoice.uid)
                .limit(25)
            )
            if invoice_scope
            else []
        )
        candidates = [
            {**row, "remaining": str(Decimal(row["total"]) - Decimal(row["allocated"]))}
            for row in invoices
            if Decimal(row["total"]) > Decimal(row["allocated"])
        ]
        party_ids = {str(party_uid)} if party_uid else set()
        party_ids.update(str(row["party_uid"]) for row in candidates)
        potential_payments = (
            self.store.read(
                select(
                    Payment.uid,
                    Payment.version,
                    Payment.name,
                    Payment.party_uid,
                    Payment.total,
                )
                .where(
                    Payment.operating_company_uid == self.company,
                    Payment.currency_uid == uid(account["currency_uid"]),
                    Payment.state == "posted",
                    Payment.kind == "customer",
                    Payment.party_uid.in_([uid(value) for value in party_ids]),
                )
                .order_by(Payment.document_date.desc())
                .limit(50)
            )
            if party_ids
            else []
        )
        payments = [
            row
            for row in potential_payments
            if Decimal(row["total"]) == Decimal(transaction.signed_amount)
        ]
        duplicates = self.store.read(
            select(
                BankMovement.uid,
                BankMovement.evidence_sha256,
                BankMovement.state,
                BankMovement.payment_uid,
            )
            .where(
                BankMovement.bank_account_uid == uid(account["uid"]),
                BankMovement.booking_date == transaction.booking_date,
                BankMovement.currency_code == transaction.currency_code,
                BankMovement.signed_amount == amount_key(transaction.signed_amount),
            )
            .order_by(BankMovement.uid)
            .limit(50)
        )
        return candidates, payments, duplicates, sorted(party_ids)

    def save_review(self, account, transaction, *, details, party=None):
        candidates, payments, duplicates, parties = self.candidate_rows(account, transaction, party)
        identifier = uuid4()
        snapshot = {
            "account_version": account["intake_version"],
            "invoices": {str(row["uid"]): row["version"] for row in candidates},
            "payments": {str(row["uid"]): row["version"] for row in payments},
            "duplicates": [str(row["uid"]) for row in duplicates],
            "parties": parties,
        }
        expiry = now() + timedelta(minutes=15)
        self.finance.transact(
            [
                insert(BankReview).values(
                    uid=identifier,
                    environment_uid=self.scope,
                    actor_uid=self.actor,
                    context=details,
                    snapshot=snapshot,
                    expires_at=expiry,
                    used_at=None,
                )
            ]
        )
        return {
            "review_uid": identifier,
            "expires_at": expiry,
            "candidate_invoices": candidates,
            "candidate_payments": payments,
            "candidate_movements": duplicates,
            "candidate_party_uids": parties,
        }

    @exact
    def resolve(self, command):
        self.finance.require("finance.read")
        connector = self.connector(command.binding)
        items = []
        for token in command.claim_tokens:
            evidence = connector.redeem(self.actor, token, "resolve")
            self.validate_evidence(connector, evidence)
            result = {"transaction": evidence.transaction, "row_locator": evidence.row_locator}
            if evidence.transaction.booking_status == "pending":
                items.append({**result, "outcome": "manual_review"})
                continue
            exact_source = self.one(
                select(BankMovementSource.__table__).where(*self.source_rule(evidence))
            )
            if exact_source:
                outcome = (
                    "already_recorded"
                    if exact_source["evidence_sha256"] == evidence.evidence_sha256
                    else "correction_review"
                )
                items.append(
                    {
                        **result,
                        "outcome": outcome,
                        "movement_uid": exact_source["movement_uid"],
                    }
                )
                continue
            mapping, account = self.mapping(evidence.installation_uid, evidence.source_account_uid)
            if not self.one(self.fence_query(command.binding, evidence)):
                raise stale()
            details = {
                "kind": "source",
                "binding": command.binding,
                "evidence": evidence.model_dump(mode="json"),
                "mapping_uid": str(mapping["uid"]),
                "mapping_version": mapping["version"],
                "account_uid": str(account["uid"]),
            }
            review = self.save_review(
                account, evidence.transaction, details=details, party=command.party_uid
            )
            items.append(
                {
                    **result,
                    **review,
                    "mapping_version": mapping["version"],
                    "outcome": "duplicate_candidate"
                    if review["candidate_movements"]
                    else "eligible",
                }
            )
        return {"items": items}

    def operation(self, key):
        return self.one(
            select(BankIntakeOperation.__table__).where(
                BankIntakeOperation.environment_uid == self.scope,
                BankIntakeOperation.actor_uid == self.actor,
                BankIntakeOperation.request_uid == key,
            )
        )

    def operation_result(self, key):
        self.finance.require("finance.read")
        row = self.operation(key)
        if not row:
            raise FinanceError(
                404, "operation_not_found", "Bank reconciliation result is unavailable"
            )
        return row["result"]

    def replay(self, command, fingerprint):
        row = self.operation(command.request_uid)
        if row:
            if row["request_sha256"] != fingerprint:
                raise FinanceError(
                    409, "request_conflict", "This request UID was already used for another action"
                )
            return row["result"]
        return None

    def review(self, key):
        review = self.one(
            select(BankReview.__table__).where(
                BankReview.uid == key,
                BankReview.environment_uid == self.scope,
                BankReview.actor_uid == self.actor,
            )
        )
        if not review or review["used_at"] is not None or instant(review["expires_at"]) <= now():
            raise stale()
        return review

    @exact
    def receipt_plan(self, payment_uid, account, transaction, command, snapshot):
        """Reuse Finance's amount normalization, company validation, posting and invoice guards."""
        self.finance.require("finance.post")
        amount = Decimal(transaction.signed_amount)
        if amount <= 0 or transaction.correction or transaction.booking_date > now().date():
            raise FinanceError(
                422, "receipt_ineligible", "Select a booked customer credit dated today or earlier"
            )
        values, _ = self.finance.prepare(
            "payments",
            {
                "name": "BANK-" + payment_uid.hex.upper(),
                "kind": "customer",
                "party_uid": command.party_uid,
                "operating_company_uid": self.company,
                "currency_uid": uid(account["currency_uid"]),
                "document_date": transaction.booking_date,
                "amount": str(amount),
                "external_reference": transaction.structured_reference
                or transaction.end_to_end_reference
                or "",
                "notes": "",
            },
            payment_uid,
        )
        if values["currency_code"] != transaction.currency_code:
            raise FinanceError(422, "company_currency", "This currency requires manual review")
        steps, allocations = [], []
        allocated = Decimal(0)
        for item in sorted(command.allocations, key=lambda entry: str(entry.invoice_uid)):
            if snapshot["invoices"].get(str(item.invoice_uid)) != item.expected_version:
                raise stale()
            invoice = self.finance.get("invoices", item.invoice_uid)
            if (
                invoice["version"] != item.expected_version
                or invoice["state"] != "posted"
                or invoice["kind"] != "customer"
                or uid(invoice["party_uid"]) != command.party_uid
                or uid(invoice["operating_company_uid"]) != self.company
                or uid(invoice["currency_uid"]) != uid(account["currency_uid"])
            ):
                raise stale()
            part = self.finance.quantize(item.amount, invoice["snapshot"], strict=True)
            if part <= 0 or part > Decimal(invoice["remaining"]):
                raise FinanceError(
                    422,
                    "allocation_amount",
                    "Allocate a positive amount within the reviewed balance",
                )
            allocated += part
            key = uuid4()
            steps.extend(
                [
                    self.finance.guard(
                        "invoices",
                        invoice,
                        item.expected_version,
                        {
                            "allocated": str(Decimal(invoice["allocated"]) + part),
                        },
                    ),
                    insert(Allocation).values(
                        uid=key,
                        invoice_uid=item.invoice_uid,
                        payment_uid=payment_uid,
                        amount=str(part),
                        state="active",
                        created_by_uid=self.actor,
                        created_at=now(),
                        reversed_at=None,
                    ),
                    self.finance.audit(
                        "invoices",
                        item.invoice_uid,
                        "allocate",
                        item.expected_version + 1,
                        ["allocated"],
                    ),
                ]
            )
            allocations.append(str(key))
        if allocated > amount:
            raise FinanceError(422, "allocation_amount", "Allocations exceed the amount received")
        stamp = now()
        values.update(
            uid=payment_uid,
            state="posted",
            allocated=str(allocated),
            version=1,
            created_at=stamp,
            updated_at=stamp,
            posted_at=stamp,
            void_reason="",
            created_by_uid=self.actor,
            updated_by_uid=self.actor,
        )
        return (
            [
                insert(Payment).values(**values),
                *self.finance.posting_steps("payments", values, "post"),
                *steps,
                self.finance.audit("payments", payment_uid, "bank-receipt", 1, values.keys()),
            ],
            allocations,
            str(amount - allocated),
        )

    def choose_payment(self, transaction, command, snapshot):
        self.finance.require("finance.post")
        payment = self.finance.get("payments", command.target_payment_uid)
        if (
            snapshot["payments"].get(str(command.target_payment_uid)) != payment["version"]
            or uid(payment["operating_company_uid"]) != self.company
            or payment["state"] != "posted"
            or payment["kind"] != "customer"
            or payment["currency_code"] != transaction.currency_code
            or Decimal(payment["total"]) != Decimal(transaction.signed_amount)
            or transaction.correction is not None
            or (command.party_uid and uid(payment["party_uid"]) != command.party_uid)
        ):
            raise stale()
        return payment

    @exact
    def save_decision(
        self, account, transaction, review, command, *, evidence=None, movement=None, guards=()
    ):
        snapshot = review["snapshot"]
        if snapshot["account_version"] != account["intake_version"]:
            raise stale()
        if command.party_uid:
            if str(command.party_uid) not in snapshot["parties"]:
                raise stale()
            self.finance.dependencies.get("parties", command.party_uid)
        steps = [*guards, self.account_guard(account)]
        payment_uid, allocation_uids, remainder = None, [], None
        party_uid = command.party_uid
        status = "unmatched" if party_uid else "needs_review"
        if transaction.correction == "reversal":
            status = "reversal_review"
        if command.reverses_movement_uid:
            original = self.movement(command.reverses_movement_uid)
            if (
                transaction.correction != "reversal"
                or original["bank_account_uid"] != account["uid"]
                or original["currency_code"] != transaction.currency_code
                or Decimal(original["signed_amount"]) * Decimal(transaction.signed_amount) >= 0
                or abs(Decimal(transaction.signed_amount)) > abs(Decimal(original["signed_amount"]))
            ):
                raise FinanceError(
                    422,
                    "invalid_reversal_link",
                    "Choose the original booking in the same account and currency",
                )
        if command.action == "link_duplicate":
            if not evidence or str(command.target_movement_uid) not in snapshot["duplicates"]:
                raise stale()
            movement_uid = command.target_movement_uid
            existing = self.movement(movement_uid)
            payment_uid = uid(existing["payment_uid"]) if existing["payment_uid"] else None
            status = "duplicate_linked"
        else:
            movement_uid = uid(movement["uid"]) if movement else uuid4()
            if evidence and snapshot["duplicates"] and not command.separate_movement_reason:
                raise FinanceError(
                    409,
                    "possible_duplicate",
                    "Link the reviewed duplicate or explain why this is a separate movement",
                )
            if movement and movement["payment_uid"]:
                raise stale()
            if command.action == "post_customer_receipt":
                payment_uid = uuid4()
                receipt_steps, allocation_uids, remainder = self.receipt_plan(
                    payment_uid,
                    account,
                    transaction,
                    command,
                    snapshot,
                )
                steps.extend(receipt_steps)
                status = "reconciled"
            elif command.action == "link_existing_payment":
                payment = self.choose_payment(transaction, command, snapshot)
                payment_uid, party_uid = uid(payment["uid"]), uid(payment["party_uid"])
                status = "reconciled"
                steps.append(
                    one_guard(
                        select(Payment.uid).where(
                            Payment.uid == payment_uid,
                            Payment.version == payment["version"],
                        ),
                        "reviewed_payment",
                    )
                )
            values = dict(
                party_uid=party_uid,
                payment_uid=payment_uid,
                state=status,
                reverses_movement_uid=command.reverses_movement_uid
                or (
                    uid(movement["reverses_movement_uid"])
                    if movement and movement["reverses_movement_uid"]
                    else None
                ),
            )
            version = 1
            if movement:
                version = movement["version"] + 1
                steps.append(
                    one_guard(
                        update(BankMovement)
                        .where(
                            BankMovement.uid == movement_uid,
                            BankMovement.version == movement["version"],
                        )
                        .values(version=version, **values)
                        .returning(BankMovement.uid),
                        "movement_version",
                    )
                )
            else:
                document = transaction.model_dump(mode="json")
                steps.append(
                    insert(BankMovement).values(
                        uid=movement_uid,
                        bank_account_uid=uid(account["uid"]),
                        booking_date=transaction.booking_date,
                        signed_amount=amount_key(transaction.signed_amount),
                        currency_code=transaction.currency_code,
                        evidence={
                            **document,
                            **(
                                {"separate_movement_reason": command.separate_movement_reason}
                                if command.separate_movement_reason
                                else {}
                            ),
                        },
                        evidence_sha256=evidence.evidence_sha256,
                        version=version,
                        actor_uid=self.actor,
                        created_at=now(),
                        **values,
                    )
                )
            steps.append(
                self.finance.audit(
                    "bank-movements", movement_uid, command.action, version, values.keys()
                )
            )
        if evidence:
            identity_kind, identity_key = evidence.identity
            steps.append(
                insert(BankMovementSource).values(
                    uid=uuid4(),
                    movement_uid=movement_uid,
                    environment_uid=self.scope,
                    installation_uid=evidence.installation_uid,
                    source_account_uid=evidence.source_account_uid,
                    identity_kind=identity_kind,
                    identity_key=identity_key,
                    statement_uid=evidence.statement_uid,
                    statement_sha256=evidence.statement_sha256,
                    row_locator=evidence.row_locator,
                    evidence_sha256=evidence.evidence_sha256,
                    adapter_key=evidence.adapter_key,
                )
            )
            if command.action == "link_duplicate":
                steps.append(
                    self.finance.audit(
                        "bank-movements",
                        movement_uid,
                        "link_duplicate",
                        existing["version"],
                        ["source"],
                    )
                )
        return steps, {
            "movement_uid": str(movement_uid),
            "outcome": status,
            "payment_uid": str(payment_uid) if payment_uid else None,
            "allocation_uids": allocation_uids,
            "unallocated_amount": remainder,
        }

    def finish(self, command, fingerprint, steps, result):
        try:
            self.finance.transact(
                [
                    one_guard(
                        update(BankReview)
                        .where(
                            BankReview.uid == command.review_uid,
                            BankReview.used_at.is_(None),
                            BankReview.expires_at > now(),
                        )
                        .values(used_at=now())
                        .returning(BankReview.uid),
                        "bank_review_version",
                    ),
                    *steps,
                    insert(BankIntakeOperation).values(
                        uid=uuid4(),
                        environment_uid=self.scope,
                        actor_uid=self.actor,
                        request_uid=command.request_uid,
                        request_sha256=fingerprint,
                        result=result,
                        created_at=now(),
                    ),
                ]
            )
        except FinanceError as exc:
            if exc.status == 409:
                existing = self.replay(command, fingerprint)
                if existing:
                    return existing
            raise
        return result

    def commit(self, command):
        self.finance.require("finance.read")
        self.finance.require("finance.write")
        fingerprint = digest(command.model_dump(mode="json"))
        existing = self.replay(command, fingerprint)
        if existing:
            return existing
        connector = self.connector(command.binding)
        evidence = connector.redeem(self.actor, command.commit_claim, "commit")
        self.validate_evidence(connector, evidence)
        review = self.review(command.review_uid)
        details = review["context"]
        if (
            details["kind"] != "source"
            or details["binding"] != command.binding
            or (Evidence.model_validate(details["evidence"]) != evidence)
            or evidence.transaction.booking_status != "booked"
        ):
            raise stale()
        mapping, account = self.mapping(evidence.installation_uid, evidence.source_account_uid)
        if (
            str(mapping["uid"]) != details["mapping_uid"]
            or str(account["uid"]) != details["account_uid"]
            or mapping["version"] != details["mapping_version"]
            or mapping["version"] != command.expected_mapping_version
        ):
            raise stale()
        guards = (
            one_guard(self.fence_query(command.binding, evidence), "bank_grant_open"),
            one_guard(
                select(BankSourceAccountMap.uid).where(
                    BankSourceAccountMap.uid == uid(mapping["uid"]),
                    BankSourceAccountMap.version == command.expected_mapping_version,
                ),
                "bank_mapping_version",
            ),
        )
        steps, result = self.save_decision(
            account,
            evidence.transaction,
            review,
            command,
            evidence=evidence,
            guards=guards,
        )
        return self.finish(command, fingerprint, steps, result)

    def movements(self, account_uid, page_index):
        self.finance.require("finance.read")
        self.account(account_uid)
        return self.store.read(
            select(BankMovement.__table__)
            .where(
                BankMovement.bank_account_uid == account_uid,
            )
            .order_by(BankMovement.booking_date.desc(), BankMovement.uid)
            .offset(page_index * 25)
            .limit(25),
            max_rows=25,
        )

    def movement(self, movement_uid):
        row = self.one(
            select(BankMovement.__table__)
            .join(BankAccount)
            .where(
                BankMovement.uid == movement_uid,
                BankAccount.environment_uid == self.scope,
                BankAccount.company_uid == self.company,
            )
        )
        if not row:
            raise FinanceError(404, "movement_unavailable", "Bank movement is unavailable")
        return row

    def transaction(self, movement):
        evidence = {
            key: value
            for key, value in movement["evidence"].items()
            if key in Transaction.model_fields
        }
        return Transaction.model_validate(evidence)

    def review_movement(self, movement_uid, party):
        self.finance.require("finance.read")
        movement = self.movement(movement_uid)
        account = self.account(movement["bank_account_uid"])
        result = self.save_review(
            account,
            self.transaction(movement),
            details={
                "kind": "movement",
                "movement_uid": str(movement_uid),
                "version": movement["version"],
            },
            party=party or (uid(movement["party_uid"]) if movement["party_uid"] else None),
        )
        result.update({"movement": movement, "expected_movement_version": movement["version"]})
        return result

    def commit_movement(self, movement_uid, command):
        self.finance.require("finance.read")
        self.finance.require("finance.write")
        fingerprint = digest([str(movement_uid), command.model_dump(mode="json")])
        existing = self.replay(command, fingerprint)
        if existing:
            return existing
        movement = self.movement(movement_uid)
        review = self.review(command.review_uid)
        if (
            review["context"]
            != {
                "kind": "movement",
                "movement_uid": str(movement_uid),
                "version": command.expected_movement_version,
            }
            or movement["version"] != command.expected_movement_version
            or command.action == "link_duplicate"
        ):
            raise stale()
        steps, result = self.save_decision(
            self.account(movement["bank_account_uid"]),
            self.transaction(movement),
            review,
            command,
            movement=movement,
        )
        return self.finish(command, fingerprint, steps, result)

    def alias(self, movement_uid, command):
        self.finance.require("finance.configure")
        movement = self.movement(movement_uid)
        fingerprint = self.transaction(movement).counterparty_fingerprint
        if not fingerprint or movement["version"] != command.expected_movement_version:
            raise stale()
        self.finance.dependencies.get("parties", command.party_uid)
        alias = self.one(
            select(BankCounterpartyAlias.__table__).where(
                BankCounterpartyAlias.environment_uid == self.scope,
                BankCounterpartyAlias.company_uid == self.company,
                BankCounterpartyAlias.fingerprint == fingerprint,
            )
        )
        if alias:
            if uid(alias["party_uid"]) != command.party_uid:
                raise FinanceError(
                    409, "alias_conflict", "The counterparty is already mapped to another party"
                )
            return {"alias_uid": alias["uid"]}
        self.finance.transact(
            [
                one_guard(
                    select(BankMovement.uid).where(
                        BankMovement.uid == movement_uid,
                        BankMovement.version == command.expected_movement_version,
                    ),
                    "movement_version",
                ),
                insert(BankCounterpartyAlias).values(
                    uid=command.request_uid,
                    environment_uid=self.scope,
                    company_uid=self.company,
                    fingerprint=fingerprint,
                    party_uid=command.party_uid,
                    actor_uid=self.actor,
                    created_at=now(),
                ),
                self.finance.audit(
                    "bank-movements",
                    movement_uid,
                    "map-counterparty",
                    movement["version"],
                    ["party_uid"],
                ),
            ]
        )
        return {"alias_uid": command.request_uid}
