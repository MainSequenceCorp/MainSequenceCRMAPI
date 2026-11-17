"""Finance-owned subledger contracts and independent SQLAlchemy metadata."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from metatables import PlatformManagedMetaTable


def field(label, description, type_, *args, **kwargs):
    return mapped_column(type_, *args, info={"label": label, "description": description}, **kwargs)


class Base(DeclarativeBase):
    metadata = MetaData()


class Owned:
    __metatable_namespace__ = "erp-finance"
    __metatable_labels__ = ["erp", "finance", "subledger"]
    uid: Mapped[UUID] = field(
        "UID", "Permanent Finance-owned record identifier.", Uuid(), primary_key=True
    )


class Document:
    name: Mapped[str] = field(
        "Reference",
        "Unique operator-entered financial document reference.",
        String(64),
        unique=True,
    )
    kind: Mapped[str] = field(
        "Kind",
        "Customer receivable/inbound receipt or vendor payable/outbound payment.",
        String(16),
    )
    state: Mapped[str] = field(
        "Status", "Draft, posted or void; posted terms are immutable.", String(16), index=True
    )
    party_uid: Mapped[UUID] = field(
        "Party", "Base customer or vendor party identifier.", Uuid(), index=True
    )
    operating_company_uid: Mapped[UUID] = field(
        "Operating company", "Base operating company owning these financial amounts.", Uuid()
    )
    currency_uid: Mapped[UUID] = field(
        "Currency", "Base currency identifier; must equal company currency.", Uuid()
    )
    party_name: Mapped[str] = field(
        "Party name", "Party name captured with financial terms.", String(511)
    )
    company_name: Mapped[str] = field(
        "Company name", "Operating company name captured with terms.", String(200)
    )
    currency_code: Mapped[str] = field(
        "Currency code", "Three-letter code for all amounts.", String(3)
    )
    document_date: Mapped[date] = field(
        "Date", "Financial document date; future documents cannot post.", Date()
    )
    notes: Mapped[str] = field("Notes", "Operator-entered financial context.", String(4000))
    snapshot: Mapped[dict] = field(
        "Reference snapshot", "Base versions and currency precision at draft save.", JSON()
    )
    total: Mapped[str] = field(
        "Total", "Exact currency-rounded total as a decimal string.", String(64)
    )
    allocated: Mapped[str] = field(
        "Allocated amount",
        "Sum of active allocations, updated atomically with allocation records.",
        String(64),
    )
    version: Mapped[int] = field(
        "Version", "Positive concurrency fence for this aggregate.", BigInteger()
    )
    created_at: Mapped[datetime] = field(
        "Created at", "UTC creation time.", DateTime(timezone=True)
    )
    updated_at: Mapped[datetime] = field(
        "Updated at", "UTC last change time.", DateTime(timezone=True)
    )
    posted_at: Mapped[datetime | None] = field(
        "Posted at", "UTC posting time, null while draft.", DateTime(timezone=True)
    )
    void_reason: Mapped[str] = field(
        "Void reason", "Reason retained for draft cancellation or posted reversal.", String(1000)
    )
    created_by_uid: Mapped[UUID] = field("Created by", "Verified platform creator.", Uuid())
    updated_by_uid: Mapped[UUID] = field("Updated by", "Verified platform editor.", Uuid())


def document_checks(prefix):
    return (
        CheckConstraint("state IN ('draft','posted','void')", name=f"ck_{prefix}_state"),
        CheckConstraint("kind IN ('customer','vendor')", name=f"ck_{prefix}_kind"),
        CheckConstraint("version > 0", name=f"ck_{prefix}_version"),
    )


class Invoice(Document, Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_finance__invoice"
    __metatable_identifier__ = "erp_finance.invoice"
    __metatable_description__ = "One customer invoice or vendor bill with exact net/tax/gross amounts, payment allocation balance, lifecycle, party/company snapshots and optional source Sales order."
    __table_args__ = document_checks("finance_invoice")
    due_date: Mapped[date] = field(
        "Due date", "Agreed payment due date, no earlier than document date.", Date()
    )
    net_total: Mapped[str] = field(
        "Net amount", "Sum of currency-rounded line net amounts.", String(64)
    )
    tax_total: Mapped[str] = field(
        "Tax amount", "Sum of manually specified simple percentage tax amounts.", String(64)
    )
    source_order_uid: Mapped[UUID | None] = field(
        "Sales order",
        "Optional unique confirmed Sales order for one full-source invoice.",
        Uuid(),
        unique=True,
    )
    source_order_name: Mapped[str | None] = field(
        "Sales reference", "Confirmed source order reference captured on creation.", String(64)
    )


class InvoiceLine(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_finance__invoice_line"
    __metatable_identifier__ = "erp_finance.invoice_line"
    __metatable_description__ = "One ordered invoice/bill line with description, positive quantity, explicit price, discount, tax percentage and exact rounded amounts."
    __table_args__ = (
        UniqueConstraint("invoice_uid", "position", name="uq_finance_invoice_line_position"),
        CheckConstraint("position >= 1", name="ck_finance_invoice_line_position"),
    )
    invoice_uid: Mapped[UUID] = field(
        "Invoice",
        "Owning Finance invoice/bill.",
        Uuid(),
        ForeignKey("erp_finance__invoice.uid", ondelete="RESTRICT"),
        index=True,
    )
    position: Mapped[int] = field("Position", "One-based stable display order.", Integer())
    description: Mapped[str] = field(
        "Description", "Financial description of goods or services.", String(4000)
    )
    quantity: Mapped[str] = field("Quantity", "Positive exact decimal quantity.", String(32))
    unit_price: Mapped[str] = field(
        "Unit price", "Nonnegative explicit price before discount and tax.", String(32)
    )
    discount: Mapped[str] = field(
        "Discount", "Percentage discount from zero through one hundred.", String(32)
    )
    tax_rate: Mapped[str] = field(
        "Tax percentage",
        "Operator-entered simple tax percentage; no rate selection or localization.",
        String(32),
    )
    net_total: Mapped[str] = field(
        "Net amount", "Rounded quantity times discounted price.", String(64)
    )
    tax_total: Mapped[str] = field(
        "Tax amount", "Rounded tax percentage of rounded net amount.", String(64)
    )
    total: Mapped[str] = field("Gross amount", "Exact sum of rounded net and tax.", String(64))
    source: Mapped[dict] = field(
        "Source snapshot", "Optional source order/line/item/unit identifiers and names.", JSON()
    )


class Payment(Document, Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_finance__payment"
    __metatable_identifier__ = "erp_finance.payment"
    __metatable_description__ = "One manually recorded customer receipt or vendor payment with company/currency, posted subledger effect and remaining unallocated amount; does not execute a bank transfer."
    __table_args__ = document_checks("finance_payment")
    external_reference: Mapped[str] = field(
        "External reference",
        "Bank or external evidence reference supplied by the operator.",
        String(200),
    )


class Allocation(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_finance__allocation"
    __metatable_identifier__ = "erp_finance.allocation"
    __metatable_description__ = "One exact payment amount allocated to a matching posted invoice or bill; retained after reversal, with both aggregate versions fenced atomically."
    __table_args__ = (
        CheckConstraint("state IN ('active','reversed')", name="ck_finance_allocation_state"),
    )
    invoice_uid: Mapped[UUID] = field(
        "Invoice",
        "Target Finance invoice or bill.",
        Uuid(),
        ForeignKey("erp_finance__invoice.uid", ondelete="RESTRICT"),
        index=True,
    )
    payment_uid: Mapped[UUID] = field(
        "Payment",
        "Source Finance receipt or payment.",
        Uuid(),
        ForeignKey("erp_finance__payment.uid", ondelete="RESTRICT"),
        index=True,
    )
    amount: Mapped[str] = field(
        "Amount", "Positive exact amount in the shared currency.", String(64)
    )
    state: Mapped[str] = field(
        "Status", "Active or reversed allocation; history is retained.", String(16)
    )
    created_at: Mapped[datetime] = field(
        "Created at", "UTC allocation time.", DateTime(timezone=True)
    )
    created_by_uid: Mapped[UUID] = field("Created by", "Verified allocating user.", Uuid())
    reversed_at: Mapped[datetime | None] = field(
        "Reversed at", "UTC reversal time, null while active.", DateTime(timezone=True)
    )


class Posting(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_finance__posting"
    __metatable_identifier__ = "erp_finance.posting"
    __metatable_description__ = "One immutable signed debit-positive/credit-negative subledger entry in a balanced invoice/payment or inventory valuation posting or its explicit reversal, with company/currency trace."
    __table_args__ = (
        UniqueConstraint(
            "resource", "record_uid", "phase", "account_role", name="uq_finance_posting_role"
        ),
        CheckConstraint("phase IN ('post','void')", name="ck_finance_posting_phase"),
    )
    resource: Mapped[str] = field(
        "Document type", "Invoices, payments or the inventory valuation source.", String(16)
    )
    record_uid: Mapped[UUID] = field("Document", "Finance document or source stock movement identifier.", Uuid(), index=True)
    operating_company_uid: Mapped[UUID] = field(
        "Company", "Base company identifier copied from the document.", Uuid()
    )
    currency_uid: Mapped[UUID] = field("Currency", "Document/company currency identifier.", Uuid())
    phase: Mapped[str] = field("Phase", "Original post or reversing void entry.", String(8))
    account_role: Mapped[str] = field(
        "Account role", "Fixed subledger role, not a configurable chart account.", String(32)
    )
    amount: Mapped[str] = field(
        "Signed amount", "Exact debit-positive or credit-negative amount.", String(64)
    )
    occurred_at: Mapped[datetime] = field(
        "Posted at", "UTC entry creation time.", DateTime(timezone=True)
    )


class AuditEvent(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_finance__audit_event"
    __metatable_identifier__ = "erp_finance.audit_event"
    __metatable_description__ = "One immutable Finance aggregate change, recording actor, action, version and changed field names in the same governed transaction."
    resource: Mapped[str] = field("Resource", "Owning Finance document collection.", String(16))
    record_uid: Mapped[UUID] = field("Record", "Finance document identifier.", Uuid(), index=True)
    action: Mapped[str] = field("Action", "Business operation performed.", String(32))
    version: Mapped[int] = field("Version", "Resulting aggregate version.", BigInteger())
    actor_uid: Mapped[UUID] = field("Actor", "Verified platform user.", Uuid())
    occurred_at: Mapped[datetime] = field(
        "Occurred at", "UTC change time.", DateTime(timezone=True)
    )
    fields: Mapped[list] = field(
        "Changed fields", "Field names affected without duplicating private payloads.", JSON()
    )


RESOURCES = {"invoices": Invoice, "payments": Payment}
MODELS = (Invoice, InvoiceLine, Payment, Allocation, Posting, AuditEvent)


def metatable_provider_models():
    return MODELS
