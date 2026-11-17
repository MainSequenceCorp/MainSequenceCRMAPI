"""Strict delivery commands; explicit versions and reconciliation identities."""

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProjectInput(Strict):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    customer_uid: UUID
    operating_company_uid: UUID
    start_date: date | None = None
    due_date: date | None = None

    @model_validator(mode="after")
    def dates(self):
        if self.start_date and self.due_date and self.due_date < self.start_date:
            raise ValueError("Due date cannot be before start date")
        return self


class TaskInput(Strict):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    project_uid: UUID
    assignee_party_uid: UUID | None = None
    due_date: date | None = None
    estimate_minutes: int = Field(default=0, strict=True, ge=0, le=1000000)


class VersionInput(Strict):
    expected_version: int = Field(strict=True, ge=1)


class ProjectCreate(ProjectInput):
    request_uid: UUID


class ProjectUpdate(ProjectInput, VersionInput):
    pass


class TaskCreate(TaskInput):
    request_uid: UUID
    expected_project_version: int = Field(strict=True, ge=1)


class TaskUpdate(TaskInput, VersionInput):
    expected_project_version: int = Field(strict=True, ge=1)


class TaskState(VersionInput):
    expected_project_version: int = Field(strict=True, ge=1)
    state: Literal["todo", "in_progress", "blocked", "done", "cancelled"]


class TimeInput(Strict):
    request_uid: UUID
    expected_task_version: int = Field(strict=True, ge=1)
    expected_project_version: int = Field(strict=True, ge=1)
    work_date: date
    minutes: int = Field(strict=True, ge=1, le=1440)
    description: str = Field(min_length=1, max_length=2000)


class VoidTime(VersionInput):
    expected_task_version: int = Field(strict=True, ge=1)
    expected_project_version: int = Field(strict=True, ge=1)
    reason: str = Field(min_length=1, max_length=1000)


class FromSales(Strict):
    request_uid: UUID
    order_uid: UUID
    expected_order_version: int = Field(strict=True, ge=1)
    name: str = Field(min_length=1, max_length=200)
    due_date: date | None = None


class BillInput(VersionInput):
    request_uid: UUID
    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z0-9][A-Z0-9._/-]*$")
    document_date: date
    due_date: date
    tax_rate: str = Field(
        default="0",
        strict=True,
        max_length=32,
        pattern=r"^(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,12})?$",
    )

    @model_validator(mode="after")
    def terms(self):
        if Decimal(self.tax_rate) > 100:
            raise ValueError("Tax percentage must be between 0 and 100")
        if self.due_date < self.document_date:
            raise ValueError("Due date cannot precede invoice date")
        return self
