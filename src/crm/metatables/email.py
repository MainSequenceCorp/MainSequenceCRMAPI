"""Email history published into CRM through explicit user selection."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from metatables import PlatformManagedMetaTable, schema_table_name

from .base import Base, VersionedRecord
from .base import column_info as info


class EmailThread(VersionedRecord, PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "email_thread")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__email_thread"
    __metatable_description__ = "One row per reviewed email conversation linked to a CRM Contact. Gmail conversations can be explicitly enrolled for new-reply synchronization by the mailbox owner."
    __metatable_labels__ = ["crm", "email", "conversation"]
    __table_args__ = (
        UniqueConstraint("source_key", "provider_thread_id", name="uq_crm_email_thread_source"),
        CheckConstraint("version > 0", name="ck_crm_email_thread_version"),
        CheckConstraint("NOT sync_enabled OR (provider_thread_id IS NOT NULL AND sync_after_ms IS NOT NULL)", name="ck_crm_email_thread_selection"),
        Index("ix_crm_email_thread_sync", "actor_uid", "sync_enabled", "last_synced_at"),
    )
    contact_uid: Mapped[uuid.UUID] = mapped_column(Uuid(), ForeignKey("mainsequence_crm__contact.uid"), nullable=False, info=info("Contact", "Reviewed Contact for this conversation."))
    interaction_uid: Mapped[uuid.UUID] = mapped_column(Uuid(), ForeignKey("mainsequence_crm__interaction.uid"), nullable=False, info=info("Interaction", "CRM conversation holding optional Company and Deal context."))
    actor_uid: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, info=info("Mailbox owner", "Verified platform actor who selected the source conversation."))
    source_key: Mapped[str] = mapped_column(String(64), nullable=False, info=info("Source identity", "Opaque stable source-account key; contains no credential."))
    provider_thread_id: Mapped[str | None] = mapped_column(String(256), info=info("Gmail thread ID", "Mailbox-scoped Gmail conversation identifier; null for manually recorded email."))
    sync_enabled: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False, info=info("Sync selected", "True only after the mailbox owner explicitly enrolls this conversation."))
    sync_after_ms: Mapped[int | None] = mapped_column(BigInteger(), info=info("Sync boundary", "Earliest Gmail internal date in epoch milliseconds eligible after explicit enrollment."))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), info=info("Last checked", "Last successful authenticated check of this selected conversation."))


class EmailMessage(VersionedRecord, PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "email_message")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__email_message"
    __metatable_description__ = "One row per explicitly captured email message or eligible reply in an enrolled conversation. Stores searchable sender, recipients, subject and plain-text body with manual or Gmail provenance."
    __metatable_labels__ = ["crm", "email", "message"]
    __table_args__ = (
        UniqueConstraint("source_key", "provider_message_id", name="uq_crm_email_message_source"),
        CheckConstraint("version > 0", name="ck_crm_email_message_version"),
        CheckConstraint("source IN ('manual','gmail')", name="ck_crm_email_message_source"),
        CheckConstraint("body_state IN ('complete','unavailable')", name="ck_crm_email_message_body"),
        Index("ix_crm_email_message_thread", "thread_uid", "internal_date_ms", "uid"),
        Index("ix_crm_email_message_date", "sent_at", "uid"),
    )
    thread_uid: Mapped[uuid.UUID] = mapped_column(Uuid(), ForeignKey("mainsequence_crm__email_thread.uid"), nullable=False, info=info("Conversation", "Reviewed conversation this message belongs to."))
    source_key: Mapped[str] = mapped_column(String(64), nullable=False, info=info("Source identity", "Opaque source-account identity used for duplicate prevention."))
    source: Mapped[str] = mapped_column(String(10), nullable=False, info=info("Provenance", "Manual entry or retrieval from the connected Gmail account."))
    provider_message_id: Mapped[str | None] = mapped_column(String(256), info=info("Gmail message ID", "Immutable Gmail message identifier in the source mailbox."))
    rfc_message_id: Mapped[str | None] = mapped_column(String(1000), info=info("RFC Message-ID", "Optional sender-supplied message header; never an authorization identity."))
    sender: Mapped[dict[str, Any]] = mapped_column(JSONB(), nullable=False, info=info("Sender", "Email address and optional sender display name."))
    to: Mapped[list[dict[str, Any]]] = mapped_column(JSONB(), nullable=False, info=info("To", "Visible primary recipient addresses and display names."))
    cc: Mapped[list[dict[str, Any]]] = mapped_column(JSONB(), nullable=False, info=info("Cc", "Visible copy recipient addresses and display names."))
    subject: Mapped[str] = mapped_column(String(2000), nullable=False, info=info("Subject", "Original message subject, independent of the shorter conversation label."))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), info=info("Sent at", "Sender-declared Date header, when valid and timezone-aware."))
    internal_date_ms: Mapped[int | None] = mapped_column(BigInteger(), info=info("Gmail internal date", "Gmail mailbox arrival timestamp in epoch milliseconds."))
    body_text: Mapped[str] = mapped_column(Text(), nullable=False, info=info("Body", "Plain-text MIME content or safely extracted HTML text, never executable markup."))
    body_state: Mapped[str] = mapped_column(String(20), nullable=False, info=info("Body availability", "Complete supported text or unavailable; never silently truncated."))
    original_url: Mapped[str | None] = mapped_column(String(2048), info=info("Original email", "Optional HTTPS reference; opening it requires source mailbox access."))


class EmailLeadLink(VersionedRecord, PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "email_lead_link")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__email_lead_link"
    __metatable_description__ = "One explicit association between a shared email Interaction and a Lead for the same Contact. Message bodies remain stored once in their source conversation."
    __metatable_labels__ = ["crm", "email", "lead", "association"]
    __table_args__ = (
        UniqueConstraint("interaction_uid", "lead_uid", name="uq_crm_email_lead_link"),
        CheckConstraint("version > 0", name="ck_crm_email_lead_link_version"),
        Index("ix_crm_email_lead_link_lead", "lead_uid", "interaction_uid"),
    )
    interaction_uid: Mapped[uuid.UUID] = mapped_column(Uuid(), ForeignKey("mainsequence_crm__interaction.uid"), nullable=False, info=info("Conversation", "Shared email Interaction explicitly published to this Lead."))
    lead_uid: Mapped[uuid.UUID] = mapped_column(Uuid(), ForeignKey("mainsequence_crm__solution_selling_lead.uid"), nullable=False, info=info("Lead", "Reviewed Lead whose Contact matches the email conversation."))
