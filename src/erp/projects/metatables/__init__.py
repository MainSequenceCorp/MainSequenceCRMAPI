"""Projects owns delivery projects, tasks and effort; CRM follow-ups stay separate."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from metatables import PlatformManagedMetaTable


def field(label, description, type_, *args, **kwargs):
    return mapped_column(type_, *args, info={"label": label, "description": description}, **kwargs)


class Base(DeclarativeBase):
    metadata = MetaData()


class Owned:
    __metatable_namespace__ = "erp-projects"
    __metatable_labels__ = ["erp", "service-delivery", "work-records"]
    uid: Mapped[UUID] = field(
        "UID", "Permanent delivery record identifier.", Uuid(), primary_key=True
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


class Project(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_projects__project"
    __metatable_identifier__ = "erp_projects.project"
    __metatable_description__ = "One customer service-delivery project with operating company, lifecycle, dates and optional commercial order and invoice trace, independent of CRM follow-ups."
    __table_args__ = (
        CheckConstraint(
            "state IN ('planned','active','delivered','closed','cancelled')",
            name="ck_projects_project_state",
        ),
        CheckConstraint("version >= 1", name="ck_projects_project_version"),
    )
    name: Mapped[str] = field("Name", "Unique project reference or name.", String(200), unique=True)
    description: Mapped[str] = field("Description", "Agreed delivery context.", String(4000))
    state: Mapped[str] = field(
        "Status", "Planned, active, delivered, closed or cancelled.", String(16), index=True
    )
    customer_uid: Mapped[UUID] = field(
        "Customer", "Base party receiving this service.", Uuid(), index=True
    )
    customer_name: Mapped[str] = field(
        "Customer name", "Customer name captured at save.", String(511)
    )
    operating_company_uid: Mapped[UUID] = field(
        "Operating company", "Base company responsible for delivery.", Uuid()
    )
    company_name: Mapped[str] = field(
        "Company name", "Operating company name captured at save.", String(200)
    )
    start_date: Mapped[date | None] = field(
        "Start date", "Planned start day; null when unspecified.", Date()
    )
    due_date: Mapped[date | None] = field(
        "Due date", "Planned delivery day; null when unspecified.", Date()
    )
    source_order_uid: Mapped[UUID | None] = field(
        "Source order",
        "Confirmed service-order identifier; null for independent projects.",
        Uuid(),
        unique=True,
    )
    source_order_name: Mapped[str | None] = field(
        "Source order name",
        "Commercial reference captured on creation; null without an order.",
        String(64),
    )
    source_snapshot: Mapped[dict] = field(
        "Source snapshot",
        "Commercial source and stable line identities captured on creation.",
        JSON(),
    )
    invoice_uid: Mapped[UUID | None] = field(
        "Invoice",
        "Finance invoice identifier created by the billing handoff; null before billing.",
        Uuid(),
        unique=True,
    )
    invoice_name: Mapped[str | None] = field(
        "Invoice reference",
        "Financial reference recorded on handoff; null before billing.",
        String(64),
    )


class DeliveryTask(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_projects__task"
    __metatable_identifier__ = "erp_projects.delivery_task"
    __metatable_description__ = "One delivery work item within a project, with state, planned effort in minutes, deadline and optional Base person assignment; not a CRM follow-up."
    __table_args__ = (
        CheckConstraint(
            "state IN ('todo','in_progress','blocked','done','cancelled')",
            name="ck_projects_task_state",
        ),
        CheckConstraint(
            "estimate_minutes >= 0 AND estimate_minutes <= 1000000",
            name="ck_projects_task_estimate",
        ),
        CheckConstraint("version >= 1", name="ck_projects_task_version"),
    )
    project_uid: Mapped[UUID] = field(
        "Project",
        "Owning delivery project identifier.",
        Uuid(),
        ForeignKey("erp_projects__project.uid", ondelete="RESTRICT"),
        index=True,
    )
    name: Mapped[str] = field("Title", "Delivery work item title.", String(200))
    description: Mapped[str] = field(
        "Description", "Work and acceptance expectations.", String(4000)
    )
    state: Mapped[str] = field(
        "Status", "Todo, in_progress, blocked, done or cancelled.", String(16), index=True
    )
    assignee_party_uid: Mapped[UUID | None] = field(
        "Assignee", "Base person identifier; null when unassigned.", Uuid()
    )
    assignee_name: Mapped[str] = field(
        "Assignee name",
        "Assigned person's name captured at save; empty when unassigned.",
        String(511),
    )
    due_date: Mapped[date | None] = field(
        "Due date", "Planned task completion day; null when unspecified.", Date()
    )
    estimate_minutes: Mapped[int] = field(
        "Estimate", "Planned whole minutes; zero when no estimate is entered.", Integer()
    )
    source_line_uid: Mapped[UUID | None] = field(
        "Source line",
        "Stable service-order line identifier; null for manually created tasks.",
        Uuid(),
        unique=True,
    )


class TimeEntry(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_projects__time_entry"
    __metatable_identifier__ = "erp_projects.time_entry"
    __metatable_description__ = "One dated whole-minute effort entry on a delivery task, with verified actor and recorded or voided history; does not calculate employee pay or invoice amounts."
    __table_args__ = (
        CheckConstraint("state IN ('recorded','voided')", name="ck_projects_time_state"),
        CheckConstraint("minutes >= 1 AND minutes <= 1440", name="ck_projects_time_minutes"),
        CheckConstraint("version >= 1", name="ck_projects_time_version"),
    )
    task_uid: Mapped[UUID] = field(
        "Task",
        "Owning delivery work item identifier.",
        Uuid(),
        ForeignKey("erp_projects__task.uid", ondelete="RESTRICT"),
        index=True,
    )
    work_date: Mapped[date] = field(
        "Work date", "Day the effort occurred, no later than today.", Date()
    )
    minutes: Mapped[int] = field("Duration", "Recorded whole minutes from 1 to 1440.", Integer())
    description: Mapped[str] = field(
        "Description", "Work performed during this entry.", String(2000)
    )
    state: Mapped[str] = field("Status", "Recorded effort or retained voided history.", String(16))
    void_reason: Mapped[str] = field(
        "Void reason", "Explanation for voiding; empty while recorded.", String(1000)
    )


class AuditEvent(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_projects__audit_event"
    __metatable_identifier__ = "erp_projects.audit_event"
    __metatable_description__ = "One immutable actor-attributed delivery mutation with resource, version and changed fields, produced with the business operation."
    resource: Mapped[str] = field("Resource", "Projects, tasks or time entries.", String(24))
    record_uid: Mapped[UUID] = field(
        "Record", "Affected delivery record identifier.", Uuid(), index=True
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


RESOURCES = {"projects": Project, "tasks": DeliveryTask, "time-entries": TimeEntry}
MODELS = (Project, DeliveryTask, TimeEntry, AuditEvent)


def metatable_provider_models():
    return MODELS
