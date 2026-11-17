"""Independent mailing records; no CRM identity, email or task graph ownership."""

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
    __metatable_namespace__ = "erp-marketing"
    __metatable_labels__ = ["erp", "marketing", "work-records"]
    uid: Mapped[UUID] = field(
        "UID", "Permanent marketing record identifier.", Uuid(), primary_key=True
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


class Subscriber(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_marketing__subscriber"
    __metatable_identifier__ = "erp_marketing.subscriber"
    __metatable_description__ = "One marketing email subscription for a shared Base person, with immutable normalized address, current subscribed or unsubscribed state and recorded evidence; not a CRM Contact."
    __table_args__ = (
        UniqueConstraint("email", name="uq_marketing_subscriber_email"),
        CheckConstraint(
            "state IN ('subscribed','unsubscribed')", name="ck_marketing_subscriber_state"
        ),
        CheckConstraint("version >= 1", name="ck_marketing_subscriber_version"),
    )
    name: Mapped[str] = field(
        "Subscriber", "Base person display name captured when subscribed.", String(511)
    )
    party_uid: Mapped[UUID] = field(
        "Person", "Immutable Base person identifier.", Uuid(), index=True
    )
    email: Mapped[str] = field(
        "Email", "Immutable normalized address; unique across subscriber records.", String(320)
    )
    state: Mapped[str] = field(
        "Status", "Subscribed or unsubscribed for all Marketing mailings.", String(16), index=True
    )
    evidence: Mapped[str] = field(
        "Evidence", "Latest explicit subscription or withdrawal evidence.", String(2000)
    )


class Mailing(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_marketing__mailing"
    __metatable_identifier__ = "erp_marketing.mailing"
    __metatable_description__ = "One bounded marketing mailing wave with reviewed plain-text content, explicit audience, lifecycle and local-capture mode; never a CRM task graph or proof of external delivery."
    __table_args__ = (
        CheckConstraint(
            "state IN ('draft','queued','completed','cancelled')", name="ck_marketing_mailing_state"
        ),
        CheckConstraint("mode = 'local_capture'", name="ck_marketing_mailing_mode"),
        CheckConstraint("version >= 1", name="ck_marketing_mailing_version"),
    )
    name: Mapped[str] = field("Name", "Internal mailing name.", String(200))
    subject: Mapped[str] = field("Subject", "Mailing subject frozen after queueing.", String(200))
    body: Mapped[str] = field("Body", "Plain-text content frozen after queueing.", String(8000))
    sender_email: Mapped[str] = field(
        "Sender", "Sender address for captured preview; not verified for outbound use.", String(320)
    )
    source_label: Mapped[str] = field(
        "Source", "Optional attribution label for this mailing.", String(200)
    )
    state: Mapped[str] = field(
        "Status", "Draft, queued, completed or cancelled.", String(16), index=True
    )
    mode: Mapped[str] = field("Mode", "local_capture only; no external email delivery.", String(24))
    queued_at: Mapped[datetime | None] = field(
        "Queued at", "UTC time audience/content was frozen.", DateTime(timezone=True)
    )
    finished_at: Mapped[datetime | None] = field(
        "Finished at", "UTC completion or cancellation time.", DateTime(timezone=True)
    )


class Recipient(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_marketing__recipient"
    __metatable_identifier__ = "erp_marketing.recipient"
    __metatable_description__ = "One unique subscriber in a mailing audience, retaining captured address/content, local result and optional existing CRM follow-up reference without owning that task."
    __table_args__ = (
        UniqueConstraint("mailing_uid", "subscriber_uid", name="uq_marketing_recipient"),
        CheckConstraint(
            "state IN ('pending','captured','suppressed','cancelled')",
            name="ck_marketing_recipient_state",
        ),
        CheckConstraint("version >= 1", name="ck_marketing_recipient_version"),
    )
    mailing_uid: Mapped[UUID] = field(
        "Mailing",
        "Owning mailing UUID.",
        Uuid(),
        ForeignKey("erp_marketing__mailing.uid", ondelete="RESTRICT"),
        index=True,
    )
    subscriber_uid: Mapped[UUID] = field(
        "Subscriber",
        "Owning marketing subscription UUID.",
        Uuid(),
        ForeignKey("erp_marketing__subscriber.uid", ondelete="RESTRICT"),
        index=True,
    )
    state: Mapped[str] = field(
        "Status",
        "Pending, captured, suppressed or cancelled; no sent/delivered claim.",
        String(16),
        index=True,
    )
    reason: Mapped[str] = field(
        "Reason", "Capture, suppression or cancellation explanation.", String(1000)
    )
    payload: Mapped[dict] = field(
        "Captured payload",
        "Immutable local snapshot of sender, address, subject and text; empty until capture.",
        JSON(),
    )
    captured_at: Mapped[datetime | None] = field(
        "Captured at", "UTC local capture time; not email delivery time.", DateTime(timezone=True)
    )
    crm_task_uid: Mapped[UUID | None] = field(
        "CRM follow-up", "Optional existing CRM-owned Task UUID.", Uuid(), index=True
    )


class DeliveryEvent(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_marketing__delivery_event"
    __metatable_identifier__ = "erp_marketing.delivery_event"
    __metatable_description__ = "One immutable local capture outcome or explicitly simulated engagement event for a mailing recipient, with operator evidence and UTC time; not a provider webhook."
    __table_args__ = (
        UniqueConstraint("recipient_uid", "kind", name="uq_marketing_delivery_event"),
        CheckConstraint("mode IN ('local_capture','simulated')", name="ck_marketing_event_mode"),
    )
    recipient_uid: Mapped[UUID] = field(
        "Recipient",
        "Owning mailing recipient UUID.",
        Uuid(),
        ForeignKey("erp_marketing__recipient.uid", ondelete="RESTRICT"),
        index=True,
    )
    kind: Mapped[str] = field(
        "Event", "Captured, suppressed, cancelled, opened, clicked, replied or bounced.", String(24)
    )
    evidence: Mapped[str] = field(
        "Evidence",
        "Operator explanation; engagement evidence is explicitly simulated.",
        String(2000),
    )
    actor_uid: Mapped[UUID] = field("Actor", "Verified operator UUID.", Uuid(), index=True)
    occurred_at: Mapped[datetime] = field(
        "Occurred at", "UTC recorded event time.", DateTime(timezone=True)
    )
    mode: Mapped[str] = field(
        "Mode", "local_capture or simulated; never an external provider observation.", String(24)
    )


class AuditEvent(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_marketing__audit_event"
    __metatable_identifier__ = "erp_marketing.audit_event"
    __metatable_description__ = "One immutable marketing mutation audit event with actor, resource, version and field names, committed with the owned business operation."
    resource: Mapped[str] = field("Resource", "Marketing resource name.", String(24))
    record_uid: Mapped[UUID] = field("Record", "Changed Marketing record UUID.", Uuid(), index=True)
    action: Mapped[str] = field("Action", "Business command name.", String(32))
    version: Mapped[int] = field("Version", "Resulting record version.", BigInteger())
    actor_uid: Mapped[UUID] = field("Actor", "Verified caller UUID.", Uuid(), index=True)
    occurred_at: Mapped[datetime] = field(
        "Occurred at", "UTC mutation time.", DateTime(timezone=True)
    )
    fields: Mapped[list] = field("Fields", "Changed field names, never message bodies.", JSON())


MODELS = [Subscriber, Mailing, Recipient, DeliveryEvent, AuditEvent]
RESOURCES = {"subscribers": Subscriber, "mailings": Mailing, "recipients": Recipient}


def metatable_provider_models():
    return list(MODELS)
