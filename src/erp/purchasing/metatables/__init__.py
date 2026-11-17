"""Purchasing-owned purchase order/order snapshots and audit; independent metadata."""

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
    __metatable_namespace__ = "erp-purchasing"
    __metatable_labels__ = ["erp", "commercial", "transactions"]
    uid: Mapped[UUID] = field(
        "UID", "Permanent Purchasing record identifier.", Uuid(), primary_key=True
    )


class Order(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_purchasing__order"
    __metatable_identifier__ = "erp_purchasing.order"
    __metatable_description__ = "One supplier purchase order or confirmed purchasing order with commercial terms, currency-rounded net amount and historical supplier/company snapshots, maintained by Purchasing."
    __table_args__ = (
        CheckConstraint(
            "state IN ('draft','rfq','confirmed','closed','cancelled')",
            name="ck_purchasing_order_state",
        ),
        CheckConstraint("version > 0", name="ck_purchasing_order_version"),
    )
    name: Mapped[str] = field(
        "Reference", "Unique commercial purchase order or order reference.", String(64), unique=True
    )
    state: Mapped[str] = field(
        "Status",
        "Draft, RFQ ready, confirmed, closed or cancelled lifecycle state.",
        String(16),
        index=True,
    )
    supplier_uid: Mapped[UUID] = field(
        "Supplier", "Base party identifier for the supplier.", Uuid(), index=True
    )
    operating_company_uid: Mapped[UUID] = field(
        "Operating company", "Base operating company identifier issuing the order.", Uuid()
    )
    currency_uid: Mapped[UUID] = field(
        "Currency", "Base currency identifier used for every amount.", Uuid()
    )
    supplier_name: Mapped[str] = field(
        "Supplier name", "Supplier name snapshotted when terms were saved.", String(511)
    )
    currency_code: Mapped[str] = field(
        "Currency code", "Three-letter currency code for the recorded amounts.", String(3)
    )
    company_name: Mapped[str] = field(
        "Company name", "Issuing operating company name snapshotted with terms.", String(200)
    )
    supplier_reference: Mapped[str] = field(
        "Supplier reference", "Reference supplied by the supplier, empty when absent.", String(200)
    )
    expected_on: Mapped[date | None] = field(
        "Valid until",
        "Expected supplier delivery date; informational, not an expiry.",
        Date(),
    )
    notes: Mapped[str] = field(
        "Terms", "Commercial notes and terms; these amounts exclude tax.", String(4000)
    )
    net_total: Mapped[str] = field(
        "Net amount",
        "Sum of rounded line amounts after discount, excluding tax, in the order currency.",
        String(64),
    )
    snapshot: Mapped[dict] = field(
        "Reference snapshot",
        "Versioned supplier, operating company and currency facts at last terms save.",
        JSON(),
    )
    bill_uid: Mapped[UUID | None] = field(
        "Vendor bill",
        "Optional unique Finance-owned draft vendor bill created for the full received order.",
        Uuid(),
        unique=True,
    )
    version: Mapped[int] = field(
        "Version", "Positive aggregate version for concurrency checks.", BigInteger()
    )
    created_at: Mapped[datetime] = field(
        "Created at", "UTC creation instant.", DateTime(timezone=True)
    )
    updated_at: Mapped[datetime] = field(
        "Updated at", "UTC last change instant.", DateTime(timezone=True)
    )
    confirmed_at: Mapped[datetime | None] = field(
        "Confirmed at",
        "UTC confirmation instant; null before confirmation.",
        DateTime(timezone=True),
    )
    created_by_uid: Mapped[UUID] = field(
        "Created by", "Verified platform creator identifier.", Uuid()
    )
    updated_by_uid: Mapped[UUID] = field(
        "Updated by", "Verified platform editor identifier.", Uuid()
    )


class OrderLine(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_purchasing__order_line"
    __metatable_identifier__ = "erp_purchasing.order_line"
    __metatable_description__ = "One ordered product or service line on a purchasing purchase order/order, with quantity, explicit unit price, percentage discount and a historical Catalog snapshot."
    __table_args__ = (
        UniqueConstraint("order_uid", "position", name="uq_purchasing_line_position"),
        CheckConstraint("position >= 1", name="ck_purchasing_line_position"),
    )
    order_uid: Mapped[UUID] = field(
        "Order",
        "Owning purchasing order identifier.",
        Uuid(),
        ForeignKey("erp_purchasing__order.uid", ondelete="RESTRICT"),
        index=True,
    )
    position: Mapped[int] = field(
        "Position", "One-based display order within the commercial document.", Integer()
    )
    item_uid: Mapped[UUID] = field("Catalog item", "Catalog product or service identifier.", Uuid())
    unit_uid: Mapped[UUID] = field(
        "Unit", "Catalog purchase unit identifier for the quantity and price.", Uuid()
    )
    description: Mapped[str] = field(
        "Description", "Supplier-facing line description.", String(4000)
    )
    quantity: Mapped[str] = field(
        "Quantity",
        "Positive quantity in the recorded purchase unit, as an exact decimal string.",
        String(32),
    )
    unit_price: Mapped[str] = field(
        "Unit price", "Nonnegative net price per unit in the order currency.", String(32)
    )
    discount: Mapped[str] = field(
        "Discount", "Percentage discount, 0 through 100 inclusive.", String(32)
    )
    net_total: Mapped[str] = field(
        "Net amount",
        "Currency-rounded quantity times price after discount, excluding tax.",
        String(64),
    )
    snapshot: Mapped[dict] = field(
        "Item snapshot", "Item/unit names, codes, kind and versions at last terms save.", JSON()
    )


class AuditEvent(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_purchasing__audit_event"
    __metatable_identifier__ = "erp_purchasing.audit_event"
    __metatable_description__ = "One immutable Purchasing order change event with action, actor, resulting version and changed field names, recorded atomically with the commercial operation."
    record_uid: Mapped[UUID] = field(
        "Record", "Affected Purchasing order identifier.", Uuid(), index=True
    )
    action: Mapped[str] = field(
        "Action", "Create, update, rfq, confirm, cancel, reopen or link operation.", String(32)
    )
    version: Mapped[int] = field("Version", "Resulting aggregate version.", BigInteger())
    actor_uid: Mapped[UUID] = field("Actor", "Verified platform actor identifier.", Uuid())
    occurred_at: Mapped[datetime] = field(
        "Occurred at", "UTC operation time.", DateTime(timezone=True)
    )
    fields: Mapped[list] = field(
        "Changed fields",
        "Names of changed fields, without their potentially sensitive values.",
        JSON(),
    )


class Receipt(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_purchasing__receipt"
    __metatable_identifier__ = "erp_purchasing.receipt"
    __metatable_description__ = "One retained full purchase-line receipt claim: service acceptance or an Inventory-owned physical movement, with revocation evidence and immutable source linkage."
    __table_args__ = (
        CheckConstraint("kind IN ('service','product')", name="ck_purchasing_receipt_kind"),
        CheckConstraint(
            "state IN ('accepted','revoked','linked')", name="ck_purchasing_receipt_state"
        ),
    )
    order_uid: Mapped[UUID] = field(
        "Order",
        "Owning purchase order.",
        Uuid(),
        ForeignKey("erp_purchasing__order.uid", ondelete="RESTRICT"),
        index=True,
    )
    line_uid: Mapped[UUID] = field(
        "Line",
        "Unique full order line receipt, retained after reversal.",
        Uuid(),
        ForeignKey("erp_purchasing__order_line.uid", ondelete="RESTRICT"),
        unique=True,
    )
    kind: Mapped[str] = field("Kind", "Service acceptance or physical product receipt.", String(16))
    state: Mapped[str] = field(
        "State",
        "Accepted/revoked service or linked physical movement; consult Inventory for physical status.",
        String(16),
    )
    movement_uid: Mapped[UUID | None] = field(
        "Movement", "Unique optional Inventory movement identifier.", Uuid(), unique=True
    )
    reason: Mapped[str] = field(
        "Evidence",
        "Reason/evidence supplied by the operator accepting or revoking service delivery.",
        String(2000),
    )
    created_at: Mapped[datetime] = field(
        "Created", "UTC receipt claim creation time.", DateTime(timezone=True)
    )
    updated_at: Mapped[datetime] = field(
        "Updated", "UTC last acceptance/revocation time.", DateTime(timezone=True)
    )
    actor_uid: Mapped[UUID] = field(
        "Actor", "Verified operator who last accepted or revoked delivery.", Uuid()
    )


MODELS = (Order, OrderLine, Receipt, AuditEvent)
