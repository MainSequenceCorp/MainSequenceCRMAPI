"""Strict People requests keep identity and version ownership on the server."""

from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Version = Annotated[int, Field(strict=True, ge=1)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VersionInput(Input):
    expected_version: Version


class Dates(Input):
    start_date: date
    end_date: date | None = None

    @model_validator(mode="after")
    def ordered(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("End date cannot precede start date")
        return self


class DepartmentInput(Input):
    name: Name
    description: str = Field(default="", max_length=2000)
    operating_company_uid: UUID


class DepartmentCreate(DepartmentInput):
    request_uid: UUID


class DepartmentUpdate(DepartmentInput, VersionInput):
    pass


class EmployeeInput(Dates):
    person_uid: UUID
    operating_company_uid: UUID
    department_uid: UUID | None = None
    job_title: str = Field(default="", max_length=200)


class EmployeeCreate(EmployeeInput):
    request_uid: UUID


class EmployeeUpdate(EmployeeInput, VersionInput):
    pass


class AbsenceInput(Dates):
    name: Name
    employee_uid: UUID
    end_date: date


class AbsenceCreate(AbsenceInput):
    request_uid: UUID
    expected_employee_version: Version


class AbsenceUpdate(AbsenceInput, VersionInput):
    expected_employee_version: Version


class AbsenceAction(VersionInput):
    expected_employee_version: Version
    note: str = Field(default="", max_length=1000)


class StaffInput(VersionInput):
    task_uid: UUID
    expected_task_version: Version
    expected_project_version: Version
