"""People owns workforce records; Base retains shared person/company identity."""

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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from metatables import PlatformManagedMetaTable


def field(label, description, type_, *args, **kwargs):
    return mapped_column(type_, *args, info={"label": label, "description": description}, **kwargs)


class Base(DeclarativeBase):
    metadata = MetaData()


class Owned:
    __metatable_namespace__ = "erp-people"
    __metatable_labels__ = ["erp", "workforce", "work-records"]
    uid: Mapped[UUID] = field(
        "UID", "Permanent workforce record identifier.", Uuid(), primary_key=True
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


class Department(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_people__department"
    __metatable_identifier__ = "erp_people.department"
    __metatable_description__ = "One flat workforce department within an operating company, with active or archived lifecycle and a name recorded by authorized People staff."
    __table_args__ = (
        UniqueConstraint("operating_company_uid", "name", name="uq_people_department_name"),
        CheckConstraint("state IN ('active','archived')", name="ck_people_department_state"),
        CheckConstraint("version >= 1", name="ck_people_department_version"),
    )
    name: Mapped[str] = field("Name", "Department name unique within its company.", String(200))
    description: Mapped[str] = field(
        "Description", "Department purpose; no private employee information.", String(2000)
    )
    operating_company_uid: Mapped[UUID] = field(
        "Company", "Base operating company identifier.", Uuid(), index=True
    )
    company_name: Mapped[str] = field(
        "Company name", "Operating company name captured at save.", String(200)
    )
    state: Mapped[str] = field("Status", "Active or archived department.", String(16))


class Employee(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_people__employee"
    __metatable_identifier__ = "erp_people.employee"
    __metatable_description__ = "One employment record for a shared person and operating company, maintained by authorized People staff with department, job title and employment dates; does not create a login or payroll record."
    __table_args__ = (
        UniqueConstraint(
            "person_uid", "operating_company_uid", name="uq_people_employee_person_company"
        ),
        CheckConstraint("state IN ('active','archived')", name="ck_people_employee_state"),
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date", name="ck_people_employee_dates"
        ),
        CheckConstraint("version >= 1", name="ck_people_employee_version"),
    )
    name: Mapped[str] = field("Name", "Shared person's name captured at save.", String(511))
    person_uid: Mapped[UUID] = field(
        "Person",
        "Permanent Base person identifier, separate from login identity.",
        Uuid(),
        index=True,
    )
    operating_company_uid: Mapped[UUID] = field(
        "Company", "Employing Base company identifier.", Uuid(), index=True
    )
    company_name: Mapped[str] = field(
        "Company name", "Employing company name captured at save.", String(200)
    )
    department_uid: Mapped[UUID | None] = field(
        "Department",
        "Same-company department identifier; null when unassigned.",
        Uuid(),
        ForeignKey("erp_people__department.uid", ondelete="RESTRICT"),
        index=True,
    )
    department_name: Mapped[str] = field(
        "Department name", "Department name captured at save; empty when unassigned.", String(200)
    )
    job_title: Mapped[str] = field("Job title", "Employee's current work role.", String(200))
    start_date: Mapped[date] = field("Start date", "First inclusive employment day.", Date())
    end_date: Mapped[date | None] = field(
        "End date", "Last inclusive employment day; null for an open employment period.", Date()
    )
    state: Mapped[str] = field(
        "Status", "Active or archived employment record.", String(16), index=True
    )


class AbsenceRequest(Owned, Tracked, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_people__absence_request"
    __metatable_identifier__ = "erp_people.absence_request"
    __metatable_description__ = "One whole-day employee absence request with inclusive calendar dates and a recorded approval decision; no entitlement balance, working calendar or payroll deduction is calculated."
    __table_args__ = (
        CheckConstraint(
            "state IN ('draft','submitted','approved','rejected','cancelled')",
            name="ck_people_absence_state",
        ),
        CheckConstraint("end_date >= start_date", name="ck_people_absence_dates"),
        CheckConstraint("version >= 1", name="ck_people_absence_version"),
    )
    name: Mapped[str] = field(
        "Description",
        "Short absence request description; avoid medical or private details.",
        String(200),
    )
    employee_uid: Mapped[UUID] = field(
        "Employee",
        "Owning employment record identifier.",
        Uuid(),
        ForeignKey("erp_people__employee.uid", ondelete="RESTRICT"),
        index=True,
    )
    employee_name: Mapped[str] = field(
        "Employee name", "Employee name captured at save.", String(511)
    )
    start_date: Mapped[date] = field("Start date", "First inclusive absence day.", Date())
    end_date: Mapped[date] = field("End date", "Last inclusive absence day.", Date())
    state: Mapped[str] = field(
        "Status", "Draft, submitted, approved, rejected or cancelled.", String(16), index=True
    )
    decision_by_uid: Mapped[UUID | None] = field(
        "Decision by", "Verified approver or rejecting actor; null before a decision.", Uuid()
    )
    decision_at: Mapped[datetime | None] = field(
        "Decision at",
        "UTC approval or rejection time; null before a decision.",
        DateTime(timezone=True),
    )
    cancellation_reason: Mapped[str] = field(
        "Cancellation reason", "Reason recorded on cancellation; empty otherwise.", String(1000)
    )
    decision_note: Mapped[str] = field(
        "Decision note",
        "Approval, rejection or cancellation context; empty before a decision.",
        String(1000),
    )


class AuditEvent(Owned, PlatformManagedMetaTable, Base):
    __tablename__ = "erp_people__audit_event"
    __metatable_identifier__ = "erp_people.audit_event"
    __metatable_description__ = "One immutable actor-attributed workforce mutation with resource, version and changed fields, produced with the business operation."
    context: Mapped[dict] = field(
        "Context", "Optional public operation lineage identifiers; empty when absent.", JSON()
    )
    resource: Mapped[str] = field("Resource", "Departments, employees or absences.", String(24))
    record_uid: Mapped[UUID] = field(
        "Record", "Affected workforce record identifier.", Uuid(), index=True
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


RESOURCES = {"departments": Department, "employees": Employee, "absences": AbsenceRequest}
MODELS = (Department, Employee, AbsenceRequest, AuditEvent)


def metatable_provider_models():
    return MODELS
