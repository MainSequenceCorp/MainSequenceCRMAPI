"""Manufacturing-owned recipes, frozen batches, work steps and atomic audit."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
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
    __metatable_namespace__ = "erp-manufacturing"
    __metatable_labels__ = ["erp", "manufacturing", "production"]
    uid: Mapped[UUID] = field(
        "UID", "Permanent Manufacturing record identifier.", Uuid(), primary_key=True
    )


class Tracked:
    version: Mapped[int] = field("Version", "Positive concurrency version.", BigInteger())
    created_at: Mapped[datetime] = field("Created", "UTC creation time.", DateTime(timezone=True))
    updated_at: Mapped[datetime] = field(
        "Updated", "UTC last change time.", DateTime(timezone=True)
    )
    created_by_uid: Mapped[UUID] = field("Creator", "Verified platform creator identity.", Uuid())
    updated_by_uid: Mapped[UUID] = field("Editor", "Verified platform last actor identity.", Uuid())


class Bom(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_manufacturing__bom"
    __metatable_identifier__ = "erp_manufacturing.bom"
    __metatable_description__ = "One single-level manufacturing bill of materials recipe with finished product output quantity, ordered operations and frozen active revision."
    __table_args__ = (
        CheckConstraint(
            "state IN ('draft','active','archived')", name="ck_manufacturing_bom_state"
        ),
        CheckConstraint("version > 0", name="ck_manufacturing_bom_version"),
    )
    name: Mapped[str] = field(
        "Reference", "Unique bill of materials reference.", String(64), unique=True
    )
    state: Mapped[str] = field(
        "Status", "Draft, active immutable recipe, or archived.", String(16), index=True
    )
    item_uid: Mapped[UUID] = field(
        "Finished product", "Catalog physical output product identifier.", Uuid(), index=True
    )
    quantity: Mapped[str] = field(
        "Output quantity", "Exact positive recipe output in the Catalog default unit.", String(32)
    )
    operations: Mapped[list] = field(
        "Operations", "Ordered operation names to copy to production work steps.", JSON()
    )
    snapshot: Mapped[dict] = field(
        "Output snapshot",
        "Output product and default unit names, versions and stock increment.",
        JSON(),
    )


class BomLine(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_manufacturing__bom_line"
    __metatable_identifier__ = "erp_manufacturing.bom_line"
    __metatable_description__ = "One unique physical component and exact quantity per manufacturing bill of materials output batch, using its Catalog default stock unit."
    __table_args__ = (
        UniqueConstraint("bom_uid", "item_uid", name="uq_manufacturing_bom_component"),
        UniqueConstraint("bom_uid", "position", name="uq_manufacturing_bom_position"),
    )
    bom_uid: Mapped[UUID] = field(
        "Bill of materials",
        "Owning Manufacturing recipe.",
        Uuid(),
        ForeignKey("erp_manufacturing__bom.uid", ondelete="RESTRICT"),
        index=True,
    )
    position: Mapped[int] = field("Position", "One-based component display order.", Integer())
    item_uid: Mapped[UUID] = field("Component", "Catalog physical component product.", Uuid())
    quantity: Mapped[str] = field(
        "Quantity", "Exact component quantity for the recipe output quantity.", String(32)
    )
    snapshot: Mapped[dict] = field(
        "Component snapshot", "Product/default-unit names, versions and increment.", JSON()
    )


class Production(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_manufacturing__production"
    __metatable_identifier__ = "erp_manufacturing.production"
    __metatable_description__ = "One full manufacturing production batch with immutable BOM and scaled material quantities, stock location references, sequential work progress and optional Finance valuation handoff."
    __table_args__ = (
        CheckConstraint(
            "state IN ('draft','ready','progress','done','cancelled')",
            name="ck_manufacturing_production_state",
        ),
        CheckConstraint("version > 0", name="ck_manufacturing_production_version"),
    )
    name: Mapped[str] = field(
        "Reference", "Unique production order reference.", String(64), unique=True
    )
    state: Mapped[str] = field(
        "Status",
        "Draft, stock reserved and ready, work in progress, done or cancelled.",
        String(16),
        index=True,
    )
    bom_uid: Mapped[UUID] = field(
        "Bill of materials",
        "Source Manufacturing recipe identifier.",
        Uuid(),
        ForeignKey("erp_manufacturing__bom.uid", ondelete="RESTRICT"),
        index=True,
    )
    operating_company_uid: Mapped[UUID] = field(
        "Company", "Base operating company for every stock policy and location.", Uuid()
    )
    quantity: Mapped[str] = field(
        "Output quantity", "Full exact output quantity in the product stock unit.", String(32)
    )
    source_uid: Mapped[UUID] = field(
        "Materials location", "Inventory internal raw-material location.", Uuid()
    )
    destination_uid: Mapped[UUID] = field(
        "Finished location", "Inventory internal finished-goods location.", Uuid()
    )
    production_location_uid: Mapped[UUID] = field(
        "Production boundary", "Inventory virtual production location; no stock balance.", Uuid()
    )
    snapshot: Mapped[dict] = field(
        "Batch snapshot",
        "Frozen recipe/version, output/component stock policies and scaled quantities, company and location names.",
        JSON(),
    )
    movement_uids: Mapped[list] = field(
        "Stock movements",
        "Complete Inventory-owned batch movement identifiers, empty before reservation.",
        JSON(),
    )
    finance_posted: Mapped[bool] = field(
        "Valuation posted", "True after all stock valuations commit to Finance together.", Boolean()
    )


class WorkStep(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_manufacturing__work_step"
    __metatable_identifier__ = "erp_manufacturing.work_step"
    __metatable_description__ = "One ordered manufacturing work operation for a production batch, with start/completion actor evidence and explicitly recorded actual minutes."
    __table_args__ = (
        UniqueConstraint("production_uid", "position", name="uq_manufacturing_work_position"),
        CheckConstraint(
            "state IN ('pending','progress','done','cancelled')", name="ck_manufacturing_step_state"
        ),
        CheckConstraint("minutes >= 0 AND minutes <= 600000", name="ck_manufacturing_step_minutes"),
    )
    production_uid: Mapped[UUID] = field(
        "Production order",
        "Owning Manufacturing batch.",
        Uuid(),
        ForeignKey("erp_manufacturing__production.uid", ondelete="RESTRICT"),
        index=True,
    )
    name: Mapped[str] = field("Operation", "Snapshotted operation name.", String(200))
    position: Mapped[int] = field("Position", "One-based required operation order.", Integer())
    state: Mapped[str] = field(
        "Status", "Pending, in progress, completed or cancelled.", String(16)
    )
    minutes: Mapped[int] = field(
        "Actual minutes",
        "Operator-recorded whole minutes, not an automatic timer or labor cost.",
        Integer(),
    )
    evidence: Mapped[str] = field(
        "Evidence", "Operator explanation of completed work.", String(2000)
    )
    started_at: Mapped[datetime | None] = field(
        "Started", "UTC operation start or null.", DateTime(timezone=True)
    )
    finished_at: Mapped[datetime | None] = field(
        "Finished", "UTC operation finish or null.", DateTime(timezone=True)
    )


class AuditEvent(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_manufacturing__audit_event"
    __metatable_identifier__ = "erp_manufacturing.audit_event"
    __metatable_description__ = "One immutable manufacturing recipe or production operation audit event with actor, action, resulting aggregate version and changed field names."
    resource: Mapped[str] = field(
        "Resource", "Affected recipe or production order family.", String(24)
    )
    record_uid: Mapped[UUID] = field("Record", "Affected aggregate identifier.", Uuid(), index=True)
    action: Mapped[str] = field("Action", "Performed business operation.", String(40))
    version: Mapped[int] = field("Version", "Resulting aggregate version.", BigInteger())
    actor_uid: Mapped[UUID] = field("Actor", "Verified platform operator identifier.", Uuid())
    occurred_at: Mapped[datetime] = field("Time", "UTC operation instant.", DateTime(timezone=True))
    fields: Mapped[list] = field(
        "Changed fields", "Changed field names without private values.", JSON()
    )


MODELS = (Bom, BomLine, Production, WorkStep, AuditEvent)
RESOURCES = {"boms": Bom, "orders": Production}
