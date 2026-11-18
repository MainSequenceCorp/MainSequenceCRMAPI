"""User Preferences owns its settings and admission metadata."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    MetaData,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from metatables import PlatformManagedMetaTable

OWNER_NAMESPACE = "erp-user-preferences"
POLICY_NAMESPACE = "erp-module-policy"
ADMISSION_NAMESPACE = "erp-module-admission"


def field(label, description, column_type, **kwargs):
    return mapped_column(column_type, info={"label": label, "description": description}, **kwargs)


class Base(DeclarativeBase):
    metadata = MetaData()


class Owned:
    __metatable_namespace__ = OWNER_NAMESPACE
    __metatable_labels__ = ["erp", "user-preferences"]

    @declared_attr
    def __tablename__(cls):
        return "erp_user_preferences__" + cls.__name__.lower()

    @declared_attr
    def __metatable_identifier__(cls):
        return "erp_user_preferences." + cls.__name__.lower()


class ScopeFields:
    environment_uid: Mapped[UUID] = field(
        "Environment", "Verified Organization Environment UID that owns this ERP data.", Uuid()
    )


class UpdatedFields:
    updated_at: Mapped[datetime] = field(
        "Updated at", "UTC time of the most recent committed update.", DateTime(timezone=True)
    )
    version: Mapped[int] = field(
        "Version", "Positive edit version used to reject concurrent changes.", BigInteger()
    )


class UserPreference(Owned, ScopeFields, UpdatedFields, PlatformManagedMetaTable, Base):
    __metatable_description__ = (
        "Private ERP sidebar preferences owned by one person in one Organization Environment."
    )
    __table_args__ = (
        UniqueConstraint("environment_uid", "person_uid", name="uq_erp_preferences_scope_person"),
        CheckConstraint("version > 0", name="ck_erp_preferences_version"),
    )
    uid: Mapped[UUID] = field(
        "UID", "Stable identifier for the personal preference.", Uuid(), primary_key=True
    )
    person_uid: Mapped[UUID] = field(
        "Person", "Verified platform person who may view and change this preference.", Uuid()
    )
    hidden_module_keys: Mapped[list[str]] = field(
        "Hidden modules", "Optional ERP module keys this person hides from navigation.", JSON()
    )


class EnvironmentModuleActivation(Owned, UpdatedFields, PlatformManagedMetaTable, Base):
    __metatable_namespaces__ = (POLICY_NAMESPACE,)
    __metatable_description__ = "Administrator policy selecting the optional ERP modules active in one Organization Environment."
    __table_args__ = (CheckConstraint("version > 0", name="ck_erp_activation_version"),)
    environment_uid: Mapped[UUID] = field(
        "Environment",
        "Verified Organization Environment UID governed by this policy.",
        Uuid(),
        primary_key=True,
    )
    active_module_keys: Mapped[list[str]] = field(
        "Active modules", "Optional modules selected by an authorized administrator.", JSON()
    )
    actor_uid: Mapped[UUID] = field(
        "Updated by", "Verified platform person responsible for the latest policy update.", Uuid()
    )


class ModuleActivationChange(Owned, ScopeFields, PlatformManagedMetaTable, Base):
    __metatable_description__ = "Append-only audit with previous and new optional ERP module settings for administrator changes."
    __table_args__ = (
        UniqueConstraint("environment_uid", "request_uid", name="uq_erp_activation_scope_request"),
        CheckConstraint("version > 0", name="ck_erp_activation_change_version"),
    )
    uid: Mapped[UUID] = field(
        "UID", "Identifier of a committed activation change.", Uuid(), primary_key=True
    )
    request_uid: Mapped[UUID] = field(
        "Request UID", "Request identifier used to reconcile a repeated activation save.", Uuid()
    )
    actor_uid: Mapped[UUID] = field(
        "Actor", "Verified platform person who made the policy change.", Uuid()
    )
    occurred_at: Mapped[datetime] = field(
        "Occurred at", "UTC time the activation change was recorded.", DateTime(timezone=True)
    )
    version: Mapped[int] = field(
        "Version", "Policy version committed by this audit entry.", BigInteger()
    )
    previous_module_keys: Mapped[list[str]] = field(
        "Previous modules", "Optional module keys active before this change.", JSON()
    )
    active_module_keys: Mapped[list[str]] = field(
        "Active modules", "Optional module keys active after this change.", JSON()
    )


class ModuleAdmissionLock(Owned, PlatformManagedMetaTable, Base):
    __metatable_namespaces__ = (ADMISSION_NAMESPACE,)
    __metatable_description__ = (
        "Environment lock for ordering activation changes and same-source business transactions."
    )
    environment_uid: Mapped[UUID] = field(
        "Environment",
        "Organization Environment that shares this transaction lock.",
        Uuid(),
        primary_key=True,
    )
    lock_marker: Mapped[int] = field(
        "Lock marker", "Value retained by the guarded update that locks this row.", BigInteger()
    )


MODELS = (
    UserPreference,
    EnvironmentModuleActivation,
    ModuleActivationChange,
    ModuleAdmissionLock,
)
ADMISSION_MODELS = (EnvironmentModuleActivation, ModuleAdmissionLock)
