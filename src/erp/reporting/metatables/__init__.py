"""Reporting-owned definitions, durable executions, snapshots and schedules."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
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
    __metatable_namespace__ = "erp-reporting"
    __metatable_labels__ = ["erp", "reporting", "automation"]
    uid: Mapped[UUID] = field(
        "UID", "Permanent reporting record identifier.", Uuid(), primary_key=True
    )


class Tracked:
    version: Mapped[int] = field("Version", "Positive concurrency version.", BigInteger())
    created_at: Mapped[datetime] = field("Created", "UTC creation time.", DateTime(timezone=True))
    updated_at: Mapped[datetime] = field(
        "Updated", "UTC last change time.", DateTime(timezone=True)
    )
    created_by_uid: Mapped[UUID] = field(
        "Creator", "Verified platform creator; also the private record owner.", Uuid(), index=True
    )
    updated_by_uid: Mapped[UUID] = field("Editor", "Verified last mutation actor.", Uuid())


class Definition(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_reporting__definition"
    __metatable_identifier__ = "erp_reporting.definition"
    __metatable_description__ = "One private saved cross-module business report definition with an approved commercial reconciliation or operations status kind and source search scope."
    __table_args__ = (
        UniqueConstraint("created_by_uid", "name", name="uq_reporting_definition_name"),
        CheckConstraint("state IN ('active','archived')", name="ck_reporting_definition_state"),
        CheckConstraint("kind IN ('commercial','operations')", name="ck_reporting_definition_kind"),
        CheckConstraint("version > 0", name="ck_reporting_definition_version"),
    )
    name: Mapped[str] = field("Name", "Saved report name within its creator scope.", String(200))
    state: Mapped[str] = field("Status", "Active for new runs or archived.", String(16), index=True)
    kind: Mapped[str] = field(
        "Report kind", "Commercial reconciliation or operations status.", String(20)
    )
    search: Mapped[str] = field(
        "Source search",
        "Literal search phrase passed to each selected owner collection; empty includes all matching records.",
        String(120),
    )


class Schedule(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_reporting__schedule"
    __metatable_identifier__ = "erp_reporting.schedule"
    __metatable_description__ = "One creator-private report automation schedule with fixed minute interval, UTC next execution time, pause state and last queued run or failure reason."
    __table_args__ = (
        UniqueConstraint("created_by_uid", "name", name="uq_reporting_schedule_name"),
        CheckConstraint("state IN ('active','paused')", name="ck_reporting_schedule_state"),
        CheckConstraint(
            "interval_minutes BETWEEN 1 AND 1440", name="ck_reporting_schedule_interval"
        ),
        CheckConstraint("version > 0", name="ck_reporting_schedule_version"),
    )
    name: Mapped[str] = field(
        "Name", "Refresh schedule name within its creator scope.", String(200)
    )
    definition_uid: Mapped[UUID] = field(
        "Saved report",
        "Owning saved report identifier.",
        Uuid(),
        ForeignKey("erp_reporting__definition.uid", ondelete="RESTRICT"),
        index=True,
    )
    state: Mapped[str] = field("Status", "Active due scheduling or paused.", String(16), index=True)
    interval_minutes: Mapped[int] = field(
        "Interval", "Fixed elapsed minutes between executions, from 1 to 1440.", Integer()
    )
    next_run_at: Mapped[datetime | None] = field(
        "Next run",
        "UTC next due time; null before first activation.",
        DateTime(timezone=True),
        index=True,
    )
    last_run_uid: Mapped[UUID | None] = field(
        "Last run", "Last execution queued by this schedule; null before any run.", Uuid()
    )
    last_error: Mapped[str] = field(
        "Last error", "Safe scheduling failure reason; empty when no scheduling error.", String(500)
    )


class Run(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_reporting__run"
    __metatable_identifier__ = "erp_reporting.run"
    __metatable_description__ = "One durable cross-module report execution with frozen definition, progress, expiring worker lease, final summary and explicit failure or recovery state."
    __table_args__ = (
        UniqueConstraint("schedule_uid", "scheduled_for", name="uq_reporting_schedule_occurrence"),
        CheckConstraint(
            "state IN ('queued','running','failed','succeeded','cancelled')",
            name="ck_reporting_run_state",
        ),
        CheckConstraint("version > 0 AND progress >= 0", name="ck_reporting_run_version"),
    )
    name: Mapped[str] = field("Name", "Saved report name captured for this execution.", String(200))
    definition_uid: Mapped[UUID] = field(
        "Saved report",
        "Source definition identifier.",
        Uuid(),
        ForeignKey("erp_reporting__definition.uid", ondelete="RESTRICT"),
        index=True,
    )
    schedule_uid: Mapped[UUID | None] = field(
        "Schedule",
        "Scheduling rule identifier; null for manual execution.",
        Uuid(),
        ForeignKey("erp_reporting__schedule.uid", ondelete="RESTRICT"),
        index=True,
    )
    scheduled_for: Mapped[datetime | None] = field(
        "Scheduled time",
        "Claimed UTC occurrence; null for manual execution.",
        DateTime(timezone=True),
    )
    state: Mapped[str] = field(
        "Status", "Queued, running, failed, succeeded or cancelled.", String(16), index=True
    )
    config: Mapped[dict] = field(
        "Definition snapshot",
        "Frozen report kind, search and definition version for this run.",
        JSON(),
    )
    progress: Mapped[int] = field("Progress", "Number of fully captured source steps.", Integer())
    lease_uid: Mapped[UUID | None] = field(
        "Lease", "Worker claim identifier; null when no step is in flight.", Uuid()
    )
    lease_until: Mapped[datetime | None] = field(
        "Lease expiry",
        "UTC claim expiry for explicit recovery; null without an active claim.",
        DateTime(timezone=True),
    )
    summary: Mapped[dict] = field(
        "Summary",
        "Final exact company/currency totals or owner/status counts, derived only from captured rows.",
        JSON(),
    )
    error: Mapped[str] = field(
        "Error",
        "Safe execution failure code and recovery guidance; empty when no failure.",
        String(500),
    )
    finished_at: Mapped[datetime | None] = field(
        "Finished",
        "UTC success, failure or cancellation time; null while queued or running.",
        DateTime(timezone=True),
    )


class RunStep(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_reporting__run_step"
    __metatable_identifier__ = "erp_reporting.run_step"
    __metatable_description__ = "One ordered report source capture step with authorized source records and versions, capture time, attempts and durable progress or failure evidence."
    __table_args__ = (
        UniqueConstraint("run_uid", "position", name="uq_reporting_step_position"),
        UniqueConstraint("run_uid", "source", name="uq_reporting_step_source"),
        CheckConstraint(
            "state IN ('pending','running','done','failed','cancelled')",
            name="ck_reporting_step_state",
        ),
        CheckConstraint("version > 0 AND attempts >= 0", name="ck_reporting_step_version"),
    )
    run_uid: Mapped[UUID] = field(
        "Run",
        "Owning report execution identifier.",
        Uuid(),
        ForeignKey("erp_reporting__run.uid", ondelete="RESTRICT"),
        index=True,
    )
    position: Mapped[int] = field("Position", "One-based source execution order.", Integer())
    source: Mapped[str] = field("Source", "Approved source business module name.", String(24))
    state: Mapped[str] = field("Status", "Pending, running, done, failed or cancelled.", String(16))
    attempts: Mapped[int] = field(
        "Attempts", "Number of claims including retries and recovered claims.", Integer()
    )
    captured_at: Mapped[datetime | None] = field(
        "Captured",
        "UTC completion time for this source snapshot; null until success.",
        DateTime(timezone=True),
    )
    records: Mapped[list] = field(
        "Source records",
        "Whitelisted immutable source values, record identifiers and versions; no credentials or raw payloads.",
        JSON(),
    )
    error: Mapped[str] = field(
        "Error", "Safe step failure and recovery guidance; empty without failure.", String(500)
    )


class AuditEvent(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_reporting__audit_event"
    __metatable_identifier__ = "erp_reporting.audit_event"
    __metatable_description__ = "One reporting or automation audit event recording verified actor, command, changed field names and resulting version without sensitive report values."
    resource: Mapped[str] = field(
        "Resource", "Definitions, runs or schedules.", String(20), index=True
    )
    record_uid: Mapped[UUID] = field(
        "Record", "Affected reporting record identifier.", Uuid(), index=True
    )
    actor_uid: Mapped[UUID] = field("Actor", "Verified platform actor identifier.", Uuid())
    action: Mapped[str] = field("Action", "Business operation name.", String(32))
    version: Mapped[int] = field("Version", "Version produced by the operation.", BigInteger())
    occurred_at: Mapped[datetime] = field(
        "Occurred", "UTC operation time.", DateTime(timezone=True)
    )
    fields: Mapped[list] = field(
        "Fields", "Changed field names without values or credentials.", JSON()
    )


MODELS = [Definition, Run, RunStep, Schedule, AuditEvent]
RESOURCES = {"definitions": Definition, "runs": Run, "schedules": Schedule}
