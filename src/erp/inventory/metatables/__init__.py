"""Inventory owns stock policy, movements and their exact physical ledger."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
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
    __metatable_namespace__ = "erp-inventory"
    __metatable_labels__ = ["erp", "inventory", "work-records"]
    uid: Mapped[UUID] = field(
        "UID", "Permanent inventory record identifier.", Uuid(), primary_key=True
    )


class Tracked:
    version: Mapped[int] = field("Version", "Positive concurrency version.", BigInteger())
    created_at: Mapped[datetime] = field(
        "Created at", "UTC creation time.", DateTime(timezone=True)
    )
    updated_at: Mapped[datetime] = field(
        "Updated at", "UTC last change time.", DateTime(timezone=True)
    )
    created_by_uid: Mapped[UUID] = field("Created by", "Verified creator identity.", Uuid())
    updated_by_uid: Mapped[UUID] = field("Updated by", "Verified last actor identity.", Uuid())


class Archivable:
    archived_at: Mapped[datetime | None] = field(
        "Archived at",
        "UTC archive time; null while available for new stock work.",
        DateTime(timezone=True),
    )


class Location(Owned, Tracked, Archivable, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_inventory__location"
    __metatable_identifier__ = "erp_inventory.location"
    __metatable_description__ = "One company stock location with internal, supplier, customer, adjustment or virtual production usage; only internal locations hold physical on-hand balances."

    __table_args__ = (
        UniqueConstraint("operating_company_uid", "code", name="uq_inventory_location_code"),
        CheckConstraint(
            "usage IN ('internal','supplier','customer','adjustment','production')",
            name="ck_inventory_location_usage",
        ),
    )
    name: Mapped[str] = field("Name", "Location display name.", String(200))
    code: Mapped[str] = field(
        "Code", "Unique location code within the operating company.", String(64)
    )
    operating_company_uid: Mapped[UUID] = field(
        "Company", "Immutable Base operating-company identifier.", Uuid(), index=True
    )
    usage: Mapped[str] = field(
        "Usage",
        "Internal stock, supplier, customer, adjustment or virtual production boundary.",
        String(16),
    )


class StockItem(Owned, Tracked, Archivable, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_inventory__stock_item"
    __metatable_identifier__ = "erp_inventory.stock_item"
    __metatable_description__ = "One immutable standard-cost stock policy for a Catalog product in an operating company, with its stock-unit increment and company currency snapshot."

    __table_args__ = (
        UniqueConstraint("operating_company_uid", "item_uid", name="uq_inventory_stock_policy"),
    )
    name: Mapped[str] = field("Product", "Catalog product name captured at setup.", String(200))
    item_uid: Mapped[UUID] = field(
        "Product identifier", "Immutable Catalog product UUID.", Uuid(), index=True
    )
    operating_company_uid: Mapped[UUID] = field(
        "Company", "Immutable Base operating-company UUID.", Uuid(), index=True
    )
    currency_uid: Mapped[UUID] = field("Currency", "Base company currency UUID at setup.", Uuid())
    unit_uid: Mapped[UUID] = field("Unit", "Catalog stock unit UUID at setup.", Uuid())
    increment: Mapped[str] = field(
        "Increment",
        "Exact positive stock unit quantity represented by one integer tick.",
        String(32),
    )
    unit_cost: Mapped[str] = field(
        "Standard cost",
        "Immutable nonnegative standard cost per stock unit, in company currency.",
        String(32),
    )
    snapshot: Mapped[dict] = field(
        "Snapshot", "Product/company/currency/unit names, versions and rounding at setup.", JSON()
    )


class Balance(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_inventory__balance"
    __metatable_identifier__ = "erp_inventory.balance"
    __metatable_description__ = "One stock product policy at an internal location, holding nonnegative on-hand and reserved quantities in exact stock-unit ticks; available equals on hand minus reserved."

    __table_args__ = (
        UniqueConstraint("stock_item_uid", "location_uid", name="uq_inventory_balance"),
        CheckConstraint(
            "on_hand_ticks >= 0 AND on_hand_ticks <= 1000000000000 AND reserved_ticks >= 0 AND reserved_ticks <= on_hand_ticks",
            name="ck_inventory_balance_quantities",
        ),
    )
    stock_item_uid: Mapped[UUID] = field(
        "Stock item",
        "Owning company product stock policy UUID.",
        Uuid(),
        ForeignKey("erp_inventory__stock_item.uid", ondelete="RESTRICT"),
        index=True,
    )
    location_uid: Mapped[UUID] = field(
        "Location",
        "Internal stock location UUID.",
        Uuid(),
        ForeignKey("erp_inventory__location.uid", ondelete="RESTRICT"),
        index=True,
    )
    on_hand_ticks: Mapped[int] = field(
        "On hand", "Nonnegative integer stock-unit ticks physically on hand.", BigInteger()
    )
    reserved_ticks: Mapped[int] = field(
        "Reserved",
        "Nonnegative integer ticks reserved by prepared outgoing movements.",
        BigInteger(),
    )


class Move(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_inventory__move"
    __metatable_identifier__ = "erp_inventory.move"
    __metatable_description__ = "One physical stock receipt, transfer, delivery or adjustment with exact quantity, reservation lifecycle, immutable completed snapshot and optional Sales source or compensating return."

    __table_args__ = (
        CheckConstraint(
            "state IN ('draft','ready','done','cancelled')", name="ck_inventory_move_state"
        ),
        CheckConstraint(
            "quantity_ticks > 0 AND quantity_ticks <= 1000000000000",
            name="ck_inventory_move_quantity",
        ),
        UniqueConstraint("sales_line_uid", name="uq_inventory_sales_line"),
        UniqueConstraint("reverses_uid", name="uq_inventory_return"),
        UniqueConstraint(
            "manufacturing_order_uid", "stock_item_uid", name="uq_inventory_production_product"
        ),
    )
    name: Mapped[str] = field("Reference", "Operator reference for this movement.", String(200))
    stock_item_uid: Mapped[UUID] = field(
        "Stock item",
        "Company product stock policy UUID.",
        Uuid(),
        ForeignKey("erp_inventory__stock_item.uid", ondelete="RESTRICT"),
        index=True,
    )
    source_uid: Mapped[UUID] = field(
        "Source",
        "Source location UUID.",
        Uuid(),
        ForeignKey("erp_inventory__location.uid", ondelete="RESTRICT"),
        index=True,
    )
    destination_uid: Mapped[UUID] = field(
        "Destination",
        "Destination location UUID.",
        Uuid(),
        ForeignKey("erp_inventory__location.uid", ondelete="RESTRICT"),
        index=True,
    )
    quantity_ticks: Mapped[int] = field(
        "Quantity ticks", "Positive quantity in snapshotted stock-unit increments.", BigInteger()
    )
    quantity: Mapped[str] = field(
        "Quantity", "Exact positive quantity expressed in the stock unit.", String(48)
    )
    kind: Mapped[str] = field(
        "Kind",
        "Receipt, delivery, transfer, adjustment_in, adjustment_out, production_in, production_out or return.",
        String(24),
    )
    state: Mapped[str] = field(
        "Status", "Draft, ready with reservation, done or cancelled.", String(16), index=True
    )
    reason: Mapped[str] = field(
        "Reason", "Operator explanation; mandatory for adjustments and returns.", String(2000)
    )
    snapshot: Mapped[dict] = field(
        "Snapshot", "Immutable product, unit, location, company and valuation context.", JSON()
    )
    net_value: Mapped[str] = field(
        "Company value",
        "Signed company inventory value change; zero for internal transfers.",
        String(64),
    )
    manufacturing_order_uid: Mapped[UUID | None] = field(
        "Manufacturing order",
        "Optional coordinated full production batch; individual movement mutations are prohibited.",
        Uuid(),
        index=True,
    )
    sales_order_uid: Mapped[UUID | None] = field(
        "Sales order",
        "Optional confirmed Sales order UUID; null for standalone movements.",
        Uuid(),
        index=True,
    )
    sales_line_uid: Mapped[UUID | None] = field(
        "Sales line",
        "Optional full-quantity Sales line claim, unique even after cancellation.",
        Uuid(),
    )
    reversal_uid: Mapped[UUID | None] = field(
        "Reversal", "Compensating full return UUID; null until returned.", Uuid()
    )
    reverses_uid: Mapped[UUID | None] = field(
        "Original move", "Original completed movement UUID when this is a full return.", Uuid()
    )
    finance_posted: Mapped[bool] = field(
        "Finance posted", "True only after an atomic Finance-owned valuation handoff.", Boolean()
    )
    completed_at: Mapped[datetime | None] = field(
        "Completed at",
        "UTC physical movement completion time; null before completion.",
        DateTime(timezone=True),
    )


class Entry(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_inventory__entry"
    __metatable_identifier__ = "erp_inventory.entry"
    __metatable_description__ = "One immutable signed stock-unit quantity and standard-cost value change at an internal location caused by a completed movement; used to reconcile on-hand balances."

    __table_args__ = (UniqueConstraint("move_uid", "location_uid", name="uq_inventory_entry"),)
    move_uid: Mapped[UUID] = field(
        "Movement",
        "Completed movement UUID.",
        Uuid(),
        ForeignKey("erp_inventory__move.uid", ondelete="RESTRICT"),
        index=True,
    )
    stock_item_uid: Mapped[UUID] = field(
        "Stock item",
        "Company product stock policy UUID.",
        Uuid(),
        ForeignKey("erp_inventory__stock_item.uid", ondelete="RESTRICT"),
        index=True,
    )
    location_uid: Mapped[UUID] = field(
        "Location",
        "Affected internal location UUID.",
        Uuid(),
        ForeignKey("erp_inventory__location.uid", ondelete="RESTRICT"),
        index=True,
    )
    quantity_ticks: Mapped[int] = field(
        "Signed ticks", "Positive receipt or negative issue in stock-unit ticks.", BigInteger()
    )
    value: Mapped[str] = field(
        "Signed value", "Signed standard-cost change in snapshotted company currency.", String(64)
    )
    occurred_at: Mapped[datetime] = field(
        "Occurred at", "UTC stock completion or reversal time.", DateTime(timezone=True)
    )


class AuditEvent(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_inventory__audit_event"
    __metatable_identifier__ = "erp_inventory.audit_event"
    __metatable_description__ = "One immutable inventory mutation audit event with actor, resource, version and field names, committed with the owned business operation."
    resource: Mapped[str] = field("Resource", "Inventory resource name.", String(24))
    record_uid: Mapped[UUID] = field("Record", "Changed Inventory record UUID.", Uuid(), index=True)
    action: Mapped[str] = field("Action", "Business command name.", String(32))
    version: Mapped[int] = field("Version", "Resulting record version.", BigInteger())
    actor_uid: Mapped[UUID] = field("Actor", "Verified caller UUID.", Uuid(), index=True)
    occurred_at: Mapped[datetime] = field(
        "Occurred at", "UTC mutation time.", DateTime(timezone=True)
    )
    fields: Mapped[list] = field("Fields", "Changed field names, never message bodies.", JSON())


MODELS = [Location, StockItem, Balance, Move, Entry, AuditEvent]
RESOURCES = {
    "locations": Location,
    "stock-items": StockItem,
    "balances": Balance,
    "movements": Move,
}


def metatable_provider_models():
    return list(MODELS)
