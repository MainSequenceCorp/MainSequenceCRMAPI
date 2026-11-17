"""Base-owned storage contracts. No CRM metadata or model imports."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    MetaData,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from metatables import PlatformManagedMetaTable


def field(label, description, type_, *args, **kwargs):
    return mapped_column(type_, *args, info={"label": label, "description": description}, **kwargs)


class Base(DeclarativeBase):
    metadata = MetaData()


class Record:
    uid: Mapped[UUID] = field("UID", "Stable Base record UUID.", Uuid(), primary_key=True)
    name: Mapped[str] = field("Name", "Human-readable business name.", String(200))
    version: Mapped[int] = field("Version", "Positive optimistic edit version.", BigInteger())
    created_at: Mapped[datetime] = field(
        "Created at", "UTC creation instant.", DateTime(timezone=True)
    )
    updated_at: Mapped[datetime] = field(
        "Updated at", "UTC last successful edit instant.", DateTime(timezone=True)
    )
    created_by_uid: Mapped[UUID] = field("Created by", "Verified platform actor UUID.", Uuid())
    updated_by_uid: Mapped[UUID] = field("Updated by", "Verified last editor UUID.", Uuid())
    archived_at: Mapped[datetime | None] = field(
        "Archived at", "UTC archive instant; null for active records.", DateTime(timezone=True)
    )
    __metatable_namespace__ = "erp-base"
    __metatable_labels__ = ["erp", "reference-data"]

    @declared_attr
    def __tablename__(cls):
        return "erp_base__" + cls.__name__.lower()

    @declared_attr
    def __metatable_identifier__(cls):
        return "erp_base." + cls.__name__.lower()


class Country(Record, PlatformManagedMetaTable, Base):
    __metatable_description__ = "One country definition with its two-letter code and display name, maintained by ERP administrators."
    __table_args__ = (
        CheckConstraint("length(code) = 2 AND code = upper(code)", name="ck_base_country_code"),
    )
    code: Mapped[str] = field(
        "Country code", "Uppercase ISO-style two-letter country code.", String(2), unique=True
    )


class Subdivision(Record, PlatformManagedMetaTable, Base):
    __metatable_description__ = "One country subdivision, state or province with its country and stable code, maintained by ERP administrators."
    country_uid: Mapped[UUID] = field(
        "Country",
        "Country containing this subdivision.",
        Uuid(),
        ForeignKey("erp_base__country.uid", ondelete="RESTRICT"),
    )
    code: Mapped[str] = field(
        "Subdivision code",
        "Unique code prefixed with the parent country code and a hyphen.",
        String(12),
        unique=True,
    )


class Language(Record, PlatformManagedMetaTable, Base):
    __metatable_description__ = "One supported communication language or regional locale definition, maintained by ERP administrators."
    code: Mapped[str] = field(
        "Language code",
        "Language tag such as en or de-AT; UI translation coverage is separate.",
        String(35),
        unique=True,
    )


class Currency(Record, PlatformManagedMetaTable, Base):
    __metatable_description__ = "One currency definition with display symbol and amount rounding precision; excludes exchange rates."
    __table_args__ = (
        CheckConstraint("minor_units BETWEEN 0 AND 6", name="ck_base_currency_precision"),
        CheckConstraint("rounding IN ('half_even', 'half_up')", name="ck_base_currency_rounding"),
        CheckConstraint("length(code) = 3 AND code = upper(code)", name="ck_base_currency_code"),
    )
    code: Mapped[str] = field(
        "Currency code", "Uppercase three-letter currency code.", String(3), unique=True
    )
    symbol: Mapped[str] = field(
        "Symbol", "Display symbol; code remains the authoritative identity.", String(12)
    )
    minor_units: Mapped[int] = field(
        "Decimal places",
        "Number of fractional decimal places, from zero through six.",
        BigInteger(),
    )
    rounding: Mapped[str] = field(
        "Rounding", "Tie-breaking convention: half_even or half_up.", String(12)
    )


class Party(Record, PlatformManagedMetaTable, Base):
    __metatable_description__ = "One person or organization business identity with contact methods and communication language; independent of CRM status."
    __metatable_labels__ = ["erp", "contacts", "organizations"]
    __table_args__ = (
        CheckConstraint("kind IN ('person', 'organization')", name="ck_base_party_kind"),
    )
    kind: Mapped[str] = field(
        "Kind", "Person or organization; immutable after creation.", String(20)
    )
    emails: Mapped[list] = field(
        "Emails", "Validated email contact addresses; an empty list means none recorded.", JSON()
    )
    phones: Mapped[list] = field(
        "Phones", "Contact phone strings; an empty list means none recorded.", JSON()
    )
    language_uid: Mapped[UUID | None] = field(
        "Language",
        "Preferred communication language; null means unspecified.",
        Uuid(),
        ForeignKey("erp_base__language.uid", ondelete="RESTRICT"),
    )


class Affiliation(Record, PlatformManagedMetaTable, Base):
    __metatable_description__ = "One dated relationship between a person and an organization, including role and historical membership."
    __table_args__ = (
        CheckConstraint(
            "ends_on IS NULL OR starts_on IS NULL OR ends_on >= starts_on",
            name="ck_base_affiliation_dates",
        ),
        CheckConstraint("person_uid != organization_uid", name="ck_base_affiliation_distinct"),
    )
    person_uid: Mapped[UUID] = field(
        "Person",
        "Person participating in the affiliation.",
        Uuid(),
        ForeignKey("erp_base__party.uid", ondelete="RESTRICT"),
    )
    organization_uid: Mapped[UUID] = field(
        "Organization",
        "Organization participating in the affiliation.",
        Uuid(),
        ForeignKey("erp_base__party.uid", ondelete="RESTRICT"),
    )
    role: Mapped[str] = field("Role", "Business relationship role or job title.", String(150))
    starts_on: Mapped[date | None] = field(
        "Starts on", "Inclusive start date; null means unknown.", Date()
    )
    ends_on: Mapped[date | None] = field(
        "Ends on", "Inclusive end date; null means open-ended.", Date()
    )


class Address(Record, PlatformManagedMetaTable, Base):
    __metatable_description__ = (
        "One postal address for a person or organization, with country and optional subdivision."
    )
    party_uid: Mapped[UUID] = field(
        "Party",
        "Person or organization using this address.",
        Uuid(),
        ForeignKey("erp_base__party.uid", ondelete="RESTRICT"),
    )
    country_uid: Mapped[UUID] = field(
        "Country",
        "Country of the postal address.",
        Uuid(),
        ForeignKey("erp_base__country.uid", ondelete="RESTRICT"),
    )
    subdivision_uid: Mapped[UUID | None] = field(
        "Subdivision",
        "Subdivision within the address country; null when unspecified.",
        Uuid(),
        ForeignKey("erp_base__subdivision.uid", ondelete="RESTRICT"),
    )
    street: Mapped[str] = field("Street", "Postal street and building lines.", String(500))
    city: Mapped[str] = field("City", "Postal city or locality.", String(150))
    postal_code: Mapped[str] = field(
        "Postal code",
        "Postal code as text, including leading zeroes; empty where not used.",
        String(30),
    )


class OperatingCompany(Record, PlatformManagedMetaTable, Base):
    __metatable_description__ = "One operating business entity linked to an organization identity, with default currency and optional parent entity."
    party_uid: Mapped[UUID] = field(
        "Organization",
        "Organization representing this operating entity.",
        Uuid(),
        ForeignKey("erp_base__party.uid", ondelete="RESTRICT"),
        unique=True,
    )
    currency_uid: Mapped[UUID] = field(
        "Currency",
        "Default transaction currency; accounting policies belong to Finance.",
        Uuid(),
        ForeignKey("erp_base__currency.uid", ondelete="RESTRICT"),
    )
    parent_uid: Mapped[UUID | None] = field(
        "Parent company",
        "Parent operating entity; null for a root entity.",
        Uuid(),
        ForeignKey("erp_base__operatingcompany.uid", ondelete="RESTRICT"),
    )


class Settings(Record, PlatformManagedMetaTable, Base):
    __metatable_description__ = "One shared ERP defaults record containing fallback language, currency, operating company and timezone."
    __table_args__ = (CheckConstraint("key = 'default'", name="ck_base_settings_singleton"),)
    key: Mapped[str] = field("Key", "Singleton key, always default.", String(12), unique=True)
    language_uid: Mapped[UUID | None] = field(
        "Language",
        "Fallback language; null when not configured.",
        Uuid(),
        ForeignKey("erp_base__language.uid", ondelete="RESTRICT"),
    )
    currency_uid: Mapped[UUID | None] = field(
        "Currency",
        "Fallback currency; null when not configured.",
        Uuid(),
        ForeignKey("erp_base__currency.uid", ondelete="RESTRICT"),
    )
    operating_company_uid: Mapped[UUID | None] = field(
        "Operating company",
        "Default operating entity; null when not configured.",
        Uuid(),
        ForeignKey("erp_base__operatingcompany.uid", ondelete="RESTRICT"),
    )
    timezone: Mapped[str] = field(
        "Timezone", "IANA timezone name used as a shared display default.", String(100)
    )


class Preference(Record, PlatformManagedMetaTable, Base):
    __metatable_description__ = "One platform person's private ERP language and timezone preferences; contains no authentication credentials."
    actor_uid: Mapped[UUID] = field(
        "Actor", "Verified platform person UUID owning these preferences.", Uuid(), unique=True
    )
    language_uid: Mapped[UUID | None] = field(
        "Language",
        "Preferred language; null uses shared defaults.",
        Uuid(),
        ForeignKey("erp_base__language.uid", ondelete="RESTRICT"),
    )
    timezone: Mapped[str] = field(
        "Timezone", "IANA timezone used for this person's display preferences.", String(100)
    )


class NumberSequence(Record, PlatformManagedMetaTable, Base):
    __metatable_description__ = "One numbered document allocation sequence scoped to an optional operating company; does not guarantee gapless legal issuance."
    __table_args__ = (
        CheckConstraint(
            "next_number > 0 AND next_number <= 999999999999999", name="ck_base_sequence_counter"
        ),
        CheckConstraint("padding BETWEEN 1 AND 12", name="ck_base_sequence_padding"),
    )
    code: Mapped[str] = field(
        "Code", "Globally unique stable sequence code.", String(60), unique=True
    )
    operating_company_uid: Mapped[UUID | None] = field(
        "Operating company",
        "Owning operating entity; null for a shared sequence.",
        Uuid(),
        ForeignKey("erp_base__operatingcompany.uid", ondelete="RESTRICT"),
    )
    prefix: Mapped[str] = field(
        "Prefix", "Literal prefix captured in every issued allocation.", String(30)
    )
    padding: Mapped[int] = field(
        "Padding", "Minimum number of digits, from one through twelve.", BigInteger()
    )
    next_number: Mapped[int] = field(
        "Next number",
        "Next allocatable positive integer, changed only by allocation.",
        BigInteger(),
    )


class Allocation(PlatformManagedMetaTable, Base):
    __tablename__ = "erp_base__allocation"
    __metatable_namespace__ = "erp-base"
    __metatable_identifier__ = "erp_base.allocation"
    __metatable_description__ = "One immutable number allocation with a retry request UUID and the rendered value at issuance."
    __metatable_labels__ = ["erp", "numbering"]
    __table_args__ = (UniqueConstraint("sequence_uid", "number", name="uq_base_allocation_number"),)
    uid: Mapped[UUID] = field(
        "Request UID",
        "Caller-supplied UUID identifying this retryable allocation request.",
        Uuid(),
        primary_key=True,
    )
    sequence_uid: Mapped[UUID] = field(
        "Sequence",
        "Sequence that issued this number.",
        Uuid(),
        ForeignKey("erp_base__numbersequence.uid", ondelete="RESTRICT"),
    )
    number: Mapped[int] = field("Number", "Allocated positive integer.", BigInteger())
    value: Mapped[str] = field(
        "Value", "Immutable rendered prefix and padded number at allocation.", String(60)
    )
    actor_uid: Mapped[UUID] = field(
        "Actor", "Verified platform actor who allocated the number.", Uuid()
    )
    created_at: Mapped[datetime] = field(
        "Created at", "UTC allocation instant.", DateTime(timezone=True)
    )


class AuditEvent(PlatformManagedMetaTable, Base):
    __tablename__ = "erp_base__auditevent"
    __metatable_namespace__ = "erp-base"
    __metatable_identifier__ = "erp_base.audit_event"
    __metatable_description__ = "One immutable Base mutation audit event identifying actor, record, resulting version and changed field names."
    __metatable_labels__ = ["erp", "audit"]
    uid: Mapped[UUID] = field("UID", "Stable audit event UUID.", Uuid(), primary_key=True)
    resource: Mapped[str] = field("Resource", "Base resource collection name.", String(40))
    record_uid: Mapped[UUID] = field(
        "Record", "Business record UUID; retained after archival.", Uuid()
    )
    action: Mapped[str] = field(
        "Action", "Create, update, archive, restore or allocate command.", String(16)
    )
    version: Mapped[int] = field("Version", "Resulting record version.", BigInteger())
    actor_uid: Mapped[UUID] = field(
        "Actor", "Verified platform actor who performed the command.", Uuid()
    )
    occurred_at: Mapped[datetime] = field(
        "Occurred at", "UTC mutation instant.", DateTime(timezone=True)
    )
    fields: Mapped[list] = field(
        "Changed fields", "Changed field names; excludes business values and credentials.", JSON()
    )


RESOURCES = {
    "countries": Country,
    "subdivisions": Subdivision,
    "languages": Language,
    "currencies": Currency,
    "parties": Party,
    "affiliations": Affiliation,
    "addresses": Address,
    "operating-companies": OperatingCompany,
    "number-sequences": NumberSequence,
    "settings": Settings,
    "preferences": Preference,
}
MODELS = [*RESOURCES.values(), Allocation, AuditEvent]
for _model in RESOURCES.values():
    _model.__table__.append_constraint(
        CheckConstraint("version > 0", name=f"ck_{_model.__tablename__}_version")
    )
    _model.__table__.append_constraint(
        CheckConstraint("length(trim(name)) > 0", name=f"ck_{_model.__tablename__}_name")
    )
