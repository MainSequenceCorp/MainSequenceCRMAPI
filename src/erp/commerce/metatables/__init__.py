"""Commerce-owned recipes, frozen batches, work steps and atomic audit."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
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
    __metatable_namespace__ = "erp-commerce"
    __metatable_labels__ = ["erp", "commerce", "website"]
    uid: Mapped[UUID] = field(
        "UID", "Permanent Commerce record identifier.", Uuid(), primary_key=True
    )


class Tracked:
    version: Mapped[int] = field("Version", "Positive concurrency version.", BigInteger())
    created_at: Mapped[datetime] = field("Created", "UTC creation time.", DateTime(timezone=True))
    updated_at: Mapped[datetime] = field(
        "Updated", "UTC last change time.", DateTime(timezone=True)
    )
    created_by_uid: Mapped[UUID] = field("Creator", "Verified platform creator identity.", Uuid())
    updated_by_uid: Mapped[UUID] = field("Editor", "Verified platform last actor identity.", Uuid())


class Site(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_commerce__site"
    __metatable_identifier__ = "erp_commerce.site"
    __metatable_description__ = "One merchant website landing page with stable public slug, plain text content, company/currency and explicit draft or published visibility."
    __table_args__ = (
        CheckConstraint("state IN ('draft','published')", name="ck_commerce_site_state"),
    )
    name: Mapped[str] = field("Title", "Public website title.", String(200))
    slug: Mapped[str] = field(
        "Address", "Stable unique public website slug.", String(80), unique=True
    )
    body: Mapped[str] = field(
        "Content", "Plain text website landing content; no HTML execution.", String(5000)
    )
    state: Mapped[str] = field(
        "Status", "Draft hidden page or published page.", String(16), index=True
    )
    operating_company_uid: Mapped[UUID] = field(
        "Company", "Immutable Base operating company.", Uuid()
    )
    currency_uid: Mapped[UUID] = field("Currency", "Immutable Base commercial currency.", Uuid())
    snapshot: Mapped[dict] = field(
        "Reference snapshot", "Company/currency names and precision at creation.", JSON()
    )


class Offer(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_commerce__offer"
    __metatable_identifier__ = "erp_commerce.offer"
    __metatable_description__ = "One website service offer with authoritative unit price, description, Catalog service/default-unit snapshot and publication state; unique service per site."
    __table_args__ = (
        UniqueConstraint("site_uid", "item_uid", name="uq_commerce_site_service"),
        CheckConstraint("state IN ('draft','published')", name="ck_commerce_offer_state"),
    )
    site_uid: Mapped[UUID] = field(
        "Website",
        "Owning Commerce website.",
        Uuid(),
        ForeignKey("erp_commerce__site.uid", ondelete="RESTRICT"),
        index=True,
    )
    item_uid: Mapped[UUID] = field("Service", "Immutable Catalog service identifier.", Uuid())
    name: Mapped[str] = field("Title", "Public service offer title.", String(200))
    description: Mapped[str] = field(
        "Description", "Public plain text service description.", String(2000)
    )
    unit_price: Mapped[str] = field(
        "Unit price", "Exact positive net unit price in website currency; excludes tax.", String(32)
    )
    state: Mapped[str] = field(
        "Status", "Draft hidden offer or published offer.", String(16), index=True
    )
    snapshot: Mapped[dict] = field(
        "Service snapshot", "Catalog service/unit name, version and quantity increment.", JSON()
    )


class PortalGrant(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_commerce__portal_grant"
    __metatable_identifier__ = "erp_commerce.portal_grant"
    __metatable_description__ = "One short-lived customer portal access grant scoped to a website and Base party, with hashed secret, expiry, revocation and version for checkout authorization."
    __table_args__ = (
        CheckConstraint("state IN ('active','revoked')", name="ck_commerce_grant_state"),
    )
    site_uid: Mapped[UUID] = field(
        "Website",
        "Owning Commerce website scope.",
        Uuid(),
        ForeignKey("erp_commerce__site.uid", ondelete="RESTRICT"),
        index=True,
    )
    customer_uid: Mapped[UUID] = field("Customer", "Authorized existing Base party.", Uuid())
    name: Mapped[str] = field(
        "Customer name", "Internal captured customer name; never public listing data.", String(511)
    )
    state: Mapped[str] = field(
        "Status", "Active until expiry or explicitly revoked.", String(16), index=True
    )
    secret_digest: Mapped[str] = field(
        "Secret digest",
        "SHA-256 digest only; raw token never persists or appears in reads.",
        String(64),
    )
    expires_at: Mapped[datetime] = field(
        "Expires", "UTC access expiry; 30 minutes after issue.", DateTime(timezone=True)
    )


class Checkout(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_commerce__checkout"
    __metatable_identifier__ = "erp_commerce.checkout"
    __metatable_description__ = "One immutable customer service checkout and frozen offer/quantity/price snapshot linked to exactly one confirmed Sales order and optional Finance invoice; original request identity supports safe recovery."
    site_uid: Mapped[UUID] = field(
        "Website",
        "Source Commerce website.",
        Uuid(),
        ForeignKey("erp_commerce__site.uid", ondelete="RESTRICT"),
        index=True,
    )
    grant_uid: Mapped[UUID] = field(
        "Portal grant",
        "Exact portal grant permitted to read this checkout.",
        Uuid(),
        ForeignKey("erp_commerce__portal_grant.uid", ondelete="RESTRICT"),
        index=True,
    )
    name: Mapped[str] = field(
        "Reference", "Generated unique checkout/order reference.", String(64), unique=True
    )
    state: Mapped[str] = field(
        "Status", "Placed checkout; payment is projected separately from Finance.", String(16)
    )
    sales_order_uid: Mapped[UUID] = field(
        "Sales order", "Unique confirmed Sales owner record.", Uuid(), unique=True
    )
    invoice_uid: Mapped[UUID | None] = field(
        "Invoice", "Optional unique Finance invoice owner record.", Uuid(), unique=True
    )
    request_hash: Mapped[str] = field(
        "Request hash", "Canonical input digest for matching original-UUID replay.", String(64)
    )
    net_total: Mapped[str] = field(
        "Net amount", "Authoritative Sales rounded amount excluding tax.", String(64)
    )
    snapshot: Mapped[dict] = field(
        "Checkout snapshot",
        "Frozen customer/company/currency and offer line quantities/prices; internal view only.",
        JSON(),
    )


class AuditEvent(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_commerce__audit_event"
    __metatable_identifier__ = "erp_commerce.audit_event"
    __metatable_description__ = "One atomic Website and commerce audit event with resource, record, actor, action, version and changed field names; no secret values or portal tokens."
    resource: Mapped[str] = field(
        "Resource", "Commerce resource collection.", String(32), index=True
    )
    record_uid: Mapped[UUID] = field(
        "Record", "Affected Commerce object identity.", Uuid(), index=True
    )
    actor_uid: Mapped[UUID] = field(
        "Actor", "Verified merchant execution identity; grant linked by checkout.", Uuid()
    )
    action: Mapped[str] = field("Action", "Executed domain operation.", String(32))
    version: Mapped[int] = field("Version", "Resulting record version.", BigInteger())
    occurred_at: Mapped[datetime] = field("Occurred", "UTC action time.", DateTime(timezone=True))
    fields: Mapped[list] = field(
        "Changed fields", "Names only; never customer token or value payload.", JSON()
    )


MODELS = (Site, Offer, PortalGrant, Checkout, AuditEvent)
RESOURCES = {"sites": Site, "offers": Offer, "grants": PortalGrant, "checkouts": Checkout}
