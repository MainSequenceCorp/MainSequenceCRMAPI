"""Catalog-owned contracts; no Base or CRM table imports."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    String,
    Uuid,
    and_,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from metatables import PlatformManagedMetaTable


def field(label, description, type_, *args, **kwargs):
    return mapped_column(type_, *args, info={"label": label, "description": description}, **kwargs)


class Base(DeclarativeBase):
    metadata = MetaData()


class Record:
    __metatable_namespace__ = "erp-catalog"
    __metatable_labels__ = ["erp", "catalog"]
    uid: Mapped[UUID] = field(
        "UID", "Permanent Catalog record identifier.", Uuid(), primary_key=True
    )
    name: Mapped[str] = field("Name", "Human-readable business name.", String(200))
    code: Mapped[str] = field(
        "Code", "Unique uppercase business code, reserved after archive.", String(64), unique=True
    )
    description: Mapped[str] = field(
        "Description", "Business explanation maintained by Catalog editors.", String(4000)
    )
    version: Mapped[int] = field(
        "Version", "Positive version for optimistic concurrency.", BigInteger()
    )
    created_at: Mapped[datetime] = field(
        "Created at", "UTC creation instant.", DateTime(timezone=True)
    )
    updated_at: Mapped[datetime] = field(
        "Updated at", "UTC last change instant.", DateTime(timezone=True)
    )
    created_by_uid: Mapped[UUID] = field("Created by", "Verified platform creator.", Uuid())
    updated_by_uid: Mapped[UUID] = field("Updated by", "Verified platform editor.", Uuid())
    archived_at: Mapped[datetime | None] = field(
        "Archived at", "UTC archive instant; null while active.", DateTime(timezone=True)
    )

    @declared_attr
    def __tablename__(cls):
        return "erp_catalog__" + cls.__name__.lower()

    @declared_attr
    def __metatable_identifier__(cls):
        return "erp_catalog." + cls.__name__.lower()


class UnitGroup(Record, PlatformManagedMetaTable, Base):
    __metatable_description__ = "One compatible quantity dimension and reference basis, such as time in hours or mass in kilograms, maintained by Catalog administrators."


class Category(Record, PlatformManagedMetaTable, Base):
    __metatable_description__ = "One product category in a non-recursive parent hierarchy used to organize products and services, maintained by Catalog administrators."
    parent_uid: Mapped[UUID | None] = field(
        "Parent category",
        "Optional parent in the product category hierarchy.",
        Uuid(),
        ForeignKey("erp_catalog__category.uid", ondelete="RESTRICT"),
        index=True,
    )


class Unit(Record, PlatformManagedMetaTable, Base):
    __metatable_description__ = "One unit of measure with a compatible quantity group, exact conversion factor and rounding precision, maintained by Catalog administrators."
    __table_args__ = (
        CheckConstraint("decimal_places BETWEEN 0 AND 12", name="ck_catalog_unit_precision"),
        CheckConstraint("NOT is_reference OR factor = '1'", name="ck_catalog_reference_factor"),
    )
    group_uid: Mapped[UUID] = field(
        "Unit group",
        "Compatible quantity dimension for conversion.",
        Uuid(),
        ForeignKey("erp_catalog__unitgroup.uid", ondelete="RESTRICT"),
    )
    factor: Mapped[str] = field(
        "Conversion factor",
        "Exact positive decimal relative to the group's reference basis; immutable.",
        String(40),
    )
    is_reference: Mapped[bool] = field(
        "Reference unit",
        "Whether this is the group's single active reference unit with factor one.",
        Boolean(),
    )
    rounding_increment: Mapped[str] = field(
        "Rounding increment",
        "Exact positive decimal quantum; conversion is rounded to its multiples.",
        String(40),
    )
    decimal_places: Mapped[int] = field(
        "Decimal places",
        "Derived display precision of the rounding increment; immutable.",
        BigInteger(),
    )


class Item(Record, PlatformManagedMetaTable, Base):
    __metatable_description__ = "One product or service definition with its default quantity unit and sale or purchase availability; excludes inventory, prices and financial balances."
    __table_args__ = (
        CheckConstraint("kind IN ('product', 'service')", name="ck_catalog_item_kind"),
    )
    kind: Mapped[str] = field("Kind", "Product or service definition.", String(12))
    unit_uid: Mapped[UUID] = field(
        "Default unit",
        "Unit for quantities of this product or service.",
        Uuid(),
        ForeignKey("erp_catalog__unit.uid", ondelete="RESTRICT"),
    )
    category_uid: Mapped[UUID] = field(
        "Product category",
        "Category organizing this product or service.",
        Uuid(),
        ForeignKey("erp_catalog__category.uid", ondelete="RESTRICT"),
        index=True,
    )
    purchase_unit_uid: Mapped[UUID] = field(
        "Purchase unit",
        "Default purchasing quantity unit, in the default unit's group.",
        Uuid(),
        ForeignKey("erp_catalog__unit.uid", ondelete="RESTRICT"),
        index=True,
    )
    sale_description: Mapped[str] = field(
        "Sales description",
        "Description for future customer-facing commercial documents.",
        String(4000),
    )
    purchase_description: Mapped[str] = field(
        "Purchase description",
        "Description for future supplier-facing commercial documents.",
        String(4000),
    )
    saleable: Mapped[bool] = field(
        "Available for sale", "Whether new sales may select this item.", Boolean()
    )
    purchasable: Mapped[bool] = field(
        "Available for purchase", "Whether new purchases may select this item.", Boolean()
    )


class AuditEvent(PlatformManagedMetaTable, Base):
    __tablename__ = "erp_catalog__auditevent"
    __metatable_identifier__ = "erp_catalog.auditevent"
    __metatable_namespace__ = "erp-catalog"
    __metatable_labels__ = ["erp", "catalog", "audit"]
    __metatable_description__ = "One successful Catalog record change with actor, time, action and changed field names, produced atomically by Catalog operations."
    uid: Mapped[UUID] = field("UID", "Unique audit event UUID.", Uuid(), primary_key=True)
    resource: Mapped[str] = field("Resource", "Catalog resource collection changed.", String(40))
    record_uid: Mapped[UUID] = field("Record", "Changed Catalog object UUID.", Uuid(), index=True)
    action: Mapped[str] = field("Action", "Create, update, archive or restore.", String(16))
    version: Mapped[int] = field("Version", "Resulting record version.", BigInteger())
    actor_uid: Mapped[UUID] = field(
        "Actor", "Verified platform identity making the change.", Uuid()
    )
    occurred_at: Mapped[datetime] = field(
        "Occurred at", "UTC successful mutation instant.", DateTime(timezone=True)
    )
    fields: Mapped[list] = field(
        "Fields", "Names of changed fields; no copied business content.", JSON()
    )


Index(
    "uq_catalog_active_reference",
    Unit.group_uid,
    unique=True,
    sqlite_where=and_(Unit.is_reference.is_(True), Unit.archived_at.is_(None)),
    postgresql_where=and_(Unit.is_reference.is_(True), Unit.archived_at.is_(None)),
)

RESOURCES = {"items": Item, "categories": Category, "units": Unit, "unit-groups": UnitGroup}
MODELS = (*RESOURCES.values(), AuditEvent)
for model in RESOURCES.values():
    model.__table__.append_constraint(
        CheckConstraint("version > 0", name=f"ck_{model.__tablename__}_version")
    )
    model.__table__.append_constraint(
        CheckConstraint("length(trim(name)) > 0", name=f"ck_{model.__tablename__}_name")
    )
