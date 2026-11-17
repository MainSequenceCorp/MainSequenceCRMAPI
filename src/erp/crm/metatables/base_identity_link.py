"""CRM-owned extraction evidence and Base profile references."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from metatables import PlatformManagedMetaTable

from .base import Base, column_info


def field(type_, label, description, **kwargs):
    return mapped_column(type_, info=column_info(label, description), **kwargs)


class BaseIdentityLink(PlatformManagedMetaTable, Base):
    __tablename__ = "mainsequence_crm__base_identity_link"
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence-crm.base_identity_link"
    __metatable_description__ = "One CRM profile or employment relationship linked to its shared directory identity, with extraction evidence retained for reconciliation and restart recovery."
    __metatable_labels__ = ["contacts", "organizations", "data-migration"]
    __table_args__ = (
        UniqueConstraint("resource", "record_uid", name="uq_crm_base_identity_record"),
    )
    uid: Mapped[UUID] = field(Uuid(), "UID", "Stable extraction link UUID.", primary_key=True)
    resource: Mapped[str] = field(
        String(40), "Resource", "CRM contacts, companies or affiliations collection."
    )
    record_uid: Mapped[UUID] = field(
        Uuid(), "CRM record", "Existing CRM record UUID, preserved through extraction."
    )
    base_uid: Mapped[UUID] = field(
        Uuid(), "Directory record", "Shared Base identity or affiliation UUID."
    )
    source_version: Mapped[int] = field(
        BigInteger(), "Source version", "CRM version copied during extraction."
    )
    source_digest: Mapped[str] = field(
        String(64), "Source digest", "SHA-256 of the canonical shared-field payload at extraction."
    )
    state: Mapped[str] = field(String(16), "State", "Copied or active adoption state.")
    created_at: Mapped[datetime] = field(
        DateTime(timezone=True), "Created at", "UTC extraction or adoption instant."
    )
    created_by_uid: Mapped[UUID] = field(
        Uuid(), "Created by", "Verified platform actor who adopted this record."
    )
