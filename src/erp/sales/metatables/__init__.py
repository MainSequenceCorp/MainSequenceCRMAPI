"""Sales-owned quotation/order snapshots and audit; independent metadata."""

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
    __metatable_namespace__ = "erp-sales"
    __metatable_labels__ = ["erp", "commercial", "transactions"]
    uid: Mapped[UUID] = field("UID", "Permanent Sales record identifier.", Uuid(), primary_key=True)


class Order(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_sales__order"
    __metatable_identifier__ = "erp_sales.order"
    __metatable_description__ = "One customer quotation or confirmed sales order with commercial terms, currency-rounded net amount and historical customer/company snapshots, maintained by Sales."
    __table_args__ = (
        CheckConstraint(
            "state IN ('draft','quoted','confirmed','cancelled')", name="ck_sales_order_state"
        ),
        CheckConstraint("version > 0", name="ck_sales_order_version"),
    )
    name: Mapped[str] = field(
        "Reference", "Unique commercial quotation or order reference.", String(64), unique=True
    )
    state: Mapped[str] = field(
        "Status", "Draft, quoted, confirmed or cancelled lifecycle state.", String(16), index=True
    )
    customer_uid: Mapped[UUID] = field(
        "Customer", "Base party identifier for the customer.", Uuid(), index=True
    )
    operating_company_uid: Mapped[UUID] = field(
        "Operating company", "Base operating company identifier issuing the order.", Uuid()
    )
    currency_uid: Mapped[UUID] = field(
        "Currency", "Base currency identifier used for every amount.", Uuid()
    )
    customer_name: Mapped[str] = field(
        "Customer name", "Customer name snapshotted when terms were saved.", String(511)
    )
    currency_code: Mapped[str] = field(
        "Currency code", "Three-letter currency code for the recorded amounts.", String(3)
    )
    company_name: Mapped[str] = field(
        "Company name", "Issuing operating company name snapshotted with terms.", String(200)
    )
    customer_reference: Mapped[str] = field(
        "Customer reference", "Reference supplied by the customer, empty when absent.", String(200)
    )
    valid_until: Mapped[date | None] = field(
        "Valid until",
        "Last UTC calendar day on which this quotation may confirm; null has no expiry.",
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
        "Versioned customer, operating company and currency facts at last terms save.",
        JSON(),
    )
    crm_deal_uid: Mapped[UUID | None] = field(
        "CRM opportunity",
        "Optional verified source opportunity identifier; null means no CRM integration.",
        Uuid(),
        index=True,
    )
    crm_deal_name: Mapped[str | None] = field(
        "Opportunity name",
        "Name of the verified source opportunity; null without a link.",
        String(511),
    )
    downstream: Mapped[dict] = field(
        "Related records",
        "Owning module and record identifiers registered by integrations.",
        JSON(),
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
    __tablename__ = "erp_sales__order_line"
    __metatable_identifier__ = "erp_sales.order_line"
    __metatable_description__ = "One ordered product or service line on a sales quotation/order, with quantity, explicit unit price, percentage discount and a historical Catalog snapshot."
    __table_args__ = (
        UniqueConstraint("order_uid", "position", name="uq_sales_line_position"),
        CheckConstraint("position >= 1", name="ck_sales_line_position"),
    )
    order_uid: Mapped[UUID] = field(
        "Order",
        "Owning sales order identifier.",
        Uuid(),
        ForeignKey("erp_sales__order.uid", ondelete="RESTRICT"),
        index=True,
    )
    position: Mapped[int] = field(
        "Position", "One-based display order within the commercial document.", Integer()
    )
    item_uid: Mapped[UUID] = field("Catalog item", "Catalog product or service identifier.", Uuid())
    unit_uid: Mapped[UUID] = field(
        "Unit", "Catalog default unit identifier for the quantity and price.", Uuid()
    )
    description: Mapped[str] = field(
        "Description", "Customer-facing line description.", String(4000)
    )
    quantity: Mapped[str] = field(
        "Quantity",
        "Positive quantity in the recorded default unit, as an exact decimal string.",
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
    __tablename__ = "erp_sales__audit_event"
    __metatable_identifier__ = "erp_sales.audit_event"
    __metatable_description__ = "One immutable Sales order change event with action, actor, resulting version and changed field names, recorded atomically with the commercial operation."
    record_uid: Mapped[UUID] = field(
        "Record", "Affected Sales order identifier.", Uuid(), index=True
    )
    action: Mapped[str] = field(
        "Action", "Create, update, quoted, confirm, cancel, reopen or link operation.", String(32)
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


MODELS = (Order, OrderLine, AuditEvent)
