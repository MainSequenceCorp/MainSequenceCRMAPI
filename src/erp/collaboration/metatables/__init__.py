"""Independent discussion records; no CRM email storage or audience changes."""

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
    __metatable_namespace__ = "erp-collaboration"
    __metatable_labels__ = ["erp", "collaboration", "work-records"]
    uid: Mapped[UUID] = field(
        "UID", "Permanent collaboration record identifier.", Uuid(), primary_key=True
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


class Discussion(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_collaboration__discussion"
    __metatable_identifier__ = "erp_collaboration.discussion"
    __metatable_description__ = "One internal shared discussion or conversation linked to an authorized delivery project, with immutable audience scope, lifecycle and ordered message counter."
    __table_args__ = (
        CheckConstraint(
            "state IN ('open','closed','archived')", name="ck_collaboration_discussion_state"
        ),
        CheckConstraint(
            "(scope='shared' AND project_uid IS NULL) OR (scope='project' AND project_uid IS NOT NULL)",
            name="ck_collaboration_discussion_scope",
        ),
        CheckConstraint(
            "version >= 1 AND message_sequence >= 0", name="ck_collaboration_discussion_counters"
        ),
    )
    name: Mapped[str] = field(
        "Subject", "Discussion subject visible only to the authorized audience.", String(200)
    )
    description: Mapped[str] = field("Description", "Plain-text discussion purpose.", String(2000))
    scope: Mapped[str] = field(
        "Scope",
        "Shared Collaboration readers or authorized project readers.",
        String(16),
        index=True,
    )
    project_uid: Mapped[UUID | None] = field(
        "Project", "Projects project identifier; null for shared discussions.", Uuid(), index=True
    )
    state: Mapped[str] = field(
        "Status", "Open, closed or archived discussion.", String(16), index=True
    )
    message_sequence: Mapped[int] = field(
        "Message sequence",
        "Last allocated message sequence; zero before the first message.",
        BigInteger(),
    )


class Message(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_collaboration__message"
    __metatable_identifier__ = "erp_collaboration.message"
    __metatable_description__ = "One actor-authored plain-text discussion message at a stable conversation sequence, retained with a retracted tombstone when withdrawn; never an imported email."
    __table_args__ = (
        UniqueConstraint("discussion_uid", "sequence", name="uq_collaboration_message_sequence"),
        CheckConstraint("state IN ('active','retracted')", name="ck_collaboration_message_state"),
        CheckConstraint("version >= 1 AND sequence >= 1", name="ck_collaboration_message_counters"),
    )
    author_name: Mapped[str] = field(
        "Author name",
        "Verified author display name captured when the message was posted.",
        String(511),
    )
    discussion_uid: Mapped[UUID] = field(
        "Discussion",
        "Owning discussion identifier and audience boundary.",
        Uuid(),
        ForeignKey("erp_collaboration__discussion.uid", ondelete="RESTRICT"),
        index=True,
    )
    sequence: Mapped[int] = field(
        "Sequence", "Positive stable order within this discussion.", BigInteger()
    )
    body: Mapped[str] = field(
        "Message", "Current plain text; empty after retraction.", String(8000)
    )
    state: Mapped[str] = field(
        "Status", "Active message or retained retracted tombstone.", String(16)
    )
    retraction_reason: Mapped[str] = field(
        "Retraction reason", "Explanation for withdrawal; empty while active.", String(1000)
    )


class MessageRevision(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_collaboration__message_revision"
    __metatable_identifier__ = "erp_collaboration.message_revision"
    __metatable_description__ = "One immutable initial, edited or retracted version of a discussion message, retained for its author and authorized moderators under the current discussion audience rules."
    __table_args__ = (
        UniqueConstraint("message_uid", "version", name="uq_collaboration_message_revision"),
        CheckConstraint("version >= 1", name="ck_collaboration_revision_version"),
    )
    actor_name: Mapped[str] = field(
        "Actor name",
        "Verified editor or moderator display name captured for this version.",
        String(511),
    )
    message_uid: Mapped[UUID] = field(
        "Message",
        "Owning discussion message identifier.",
        Uuid(),
        ForeignKey("erp_collaboration__message.uid", ondelete="RESTRICT"),
        index=True,
    )
    version: Mapped[int] = field(
        "Version", "Positive immutable message content version.", BigInteger()
    )
    body: Mapped[str] = field(
        "Message", "Plain text of this version; empty for the retraction version.", String(8000)
    )
    state: Mapped[str] = field("Status", "Active or retracted at this version.", String(16))
    reason: Mapped[str] = field(
        "Reason", "Retraction context; empty for initial or edited text.", String(1000)
    )
    actor_uid: Mapped[UUID] = field("Actor", "Verified actor who authored this version.", Uuid())
    occurred_at: Mapped[datetime] = field(
        "Occurred at", "UTC version creation time.", DateTime(timezone=True)
    )


class AuditEvent(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_collaboration__audit_event"
    __metatable_identifier__ = "erp_collaboration.audit_event"
    __metatable_description__ = "One immutable actor-attributed discussion mutation with resource, version and changed fields, produced with the business operation."
    context: Mapped[dict] = field(
        "Context",
        "Message identity and version for content operations; empty for discussion changes.",
        JSON(),
    )
    resource: Mapped[str] = field("Resource", "Discussions.", String(24))
    record_uid: Mapped[UUID] = field(
        "Record", "Affected discussion record identifier.", Uuid(), index=True
    )
    action: Mapped[str] = field("Action", "Business operation recorded.", String(32))
    version: Mapped[int] = field("Version", "Version produced by the operation.", BigInteger())
    actor_uid: Mapped[UUID] = field("Actor", "Verified mutation actor identifier.", Uuid())
    occurred_at: Mapped[datetime] = field(
        "Occurred at", "UTC operation time.", DateTime(timezone=True)
    )
    fields: Mapped[list] = field(
        "Fields", "Names of changed fields without sensitive values.", JSON()
    )


RESOURCES = {"discussions": Discussion, "messages": Message}
MODELS = (Discussion, Message, MessageRevision, AuditEvent)


def metatable_provider_models():
    return MODELS
