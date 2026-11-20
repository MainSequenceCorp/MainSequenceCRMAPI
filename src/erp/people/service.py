"""Workforce lifecycle and approval rules over governed, version-fenced transactions."""

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, insert, or_, select, update

from mainsequence.client.exceptions import BadRequestError
from metatables import MetaTableTransactionGuardError
from metatables.compiled_sql.v1 import GuardedStatement
from src.erp.collections import read_page
from src.erp.module_access import require_module

from .errors import PeopleError
from .metatables import RESOURCES, AbsenceRequest, AuditEvent, Department, Employee
from .schemas import AbsenceInput, DepartmentInput, EmployeeInput, StaffInput


def key(value):
    return UUID(str(value))


def now():
    return datetime.now(timezone.utc)


def day(value):
    return date.fromisoformat(str(value))


class Service:
    def __init__(self, store, actor_uid, capabilities, dependencies):
        self.store, self.actor_uid, self.capabilities, self.dependencies = (
            store,
            key(actor_uid),
            set(capabilities),
            dependencies,
        )

    def require(self, cap):
        require_module("people")
        if cap not in self.capabilities:
            raise PeopleError(403, "forbidden", "People access does not permit this operation")

    def row(self, resource, uid):
        self.require("people.read")
        if resource not in RESOURCES:
            raise PeopleError(404, "not_found", "Unknown People resource")
        model = RESOURCES[resource]
        rows = self.store.read(select(model.__table__).where(model.uid == key(uid)).limit(1))
        if not rows:
            raise PeopleError(404, "not_found", "People record not found")
        return rows[0]

    def get(self, resource, uid):
        row = self.row(resource, uid)
        if resource == "absences":
            employee = self.row("employees", row["employee_uid"])
            row.update(
                employee_version=employee["version"],
                employee_state=employee["state"],
                calendar_days=(day(row["end_date"]) - day(row["start_date"])).days + 1,
            )
        if resource == "departments":
            row["active_members"] = self.count(
                Employee, Employee.department_uid == key(uid), Employee.state == "active"
            )
        return row

    def count(self, model, *terms):
        return int(
            self.store.read(select(func.count().label("count")).select_from(model).where(*terms))[
                0
            ]["count"]
        )

    def collection(
        self,
        resource,
        *,
        page_index=0,
        page_size=25,
        search="",
        state=None,
        employee_uid=None,
        operating_company_uid=None,
    ):
        self.require("people.read")
        if resource not in RESOURCES:
            raise PeopleError(404, "not_found", "Unknown People collection")
        model = RESOURCES[resource]
        terms = []
        if search:
            terms.append(func.lower(model.name).contains(search.lower(), autoescape=True))
        if state:
            terms.append(model.state == state)
        parent = None
        if employee_uid:
            if resource != "absences":
                raise PeopleError(422, "filter", "Employee filter requires absence requests")
            parent = (
                select(Employee.uid).where(Employee.uid == key(employee_uid)).exists(),
                PeopleError(404, "not_found", "People record not found"),
            )
            terms.append(model.employee_uid == key(employee_uid))
        if operating_company_uid:
            if resource == "absences":
                raise PeopleError(422, "filter", "Company filter requires departments or employees")
            terms.append(model.operating_company_uid == key(operating_company_uid))
        return read_page(
            self.store,
            model.__table__,
            terms,
            (model.name, model.uid),
            page_index=page_index,
            page_size=page_size,
            parent=parent,
        )

    def transact(self, steps):
        try:
            return self.store.write(steps)
        except MetaTableTransactionGuardError as exc:
            raise PeopleError(
                409, "conflict", "People or delivery record changed; reload and review"
            ) from exc
        except BadRequestError as exc:
            detail = (getattr(exc, "payload", {}) or {}).get("detail", {})
            if isinstance(detail, dict) and detail.get("code") == "compiled_sql_database_error":
                raise PeopleError(
                    409,
                    "constraint_conflict",
                    "Record or request already exists; check the saved record",
                ) from exc
            raise

    def created(self):
        return dict(
            version=1,
            created_at=now(),
            updated_at=now(),
            created_by_uid=self.actor_uid,
            updated_by_uid=self.actor_uid,
        )

    def audit(self, resource, uid, action, version, fields, context=None):
        return insert(AuditEvent).values(
            uid=uuid4(),
            resource=resource,
            record_uid=key(uid),
            action=action,
            version=version,
            actor_uid=self.actor_uid,
            occurred_at=now(),
            fields=sorted(fields),
            context=context or {},
        )

    def guard(self, resource, row, expected, values):
        model = RESOURCES[resource]
        return GuardedStatement(
            update(model)
            .where(
                model.uid == key(row["uid"]), model.version == expected, model.state == row["state"]
            )
            .values(**values, version=expected + 1, updated_at=now(), updated_by_uid=self.actor_uid)
            .returning(model.uid),
            expect_rows=1,
            label=resource + "_version",
        )

    def active(self, row):
        if row["state"] != "active":
            raise PeopleError(409, "inactive", "Restore the workforce record before changing it")

    def company(self, uid):
        company = self.dependencies.base_record("operating-companies", uid)
        self.dependencies.base_record("parties", company["party_uid"])
        return company

    def save_department(self, payload, *, uid=None, expected_version=None, request_uid=None):
        self.require("people.write")
        data = DepartmentInput.model_validate(payload).model_dump()
        data["company_name"] = self.company(data["operating_company_uid"])["name"]
        if uid:
            old = self.row("departments", uid)
            self.active(old)
            if str(data["operating_company_uid"]) != old["operating_company_uid"]:
                raise PeopleError(422, "company", "Department company cannot change")
            steps = [self.guard("departments", old, expected_version, data)]
            version = expected_version + 1
        else:
            uid, version = request_uid or uuid4(), 1
            steps = [
                insert(Department).values(uid=key(uid), **data, **self.created(), state="active")
            ]
        self.transact(
            [
                *steps,
                self.audit(
                    "departments", uid, "update" if expected_version else "create", version, data
                ),
            ]
        )
        return self.get("departments", uid)

    def membership_steps(self, old_department, new_department):
        steps = []
        for uid in sorted({str(x) for x in [old_department, new_department] if x}):
            department = self.row("departments", uid)
            if str(new_department) == uid:
                self.active(department)
            steps += [
                self.guard("departments", department, department["version"], {}),
                self.audit(
                    "departments", uid, "membership", department["version"] + 1, ["members"]
                ),
            ]
        return steps

    def save_employee(self, payload, *, uid=None, expected_version=None, request_uid=None):
        self.require("people.write")
        data = EmployeeInput.model_validate(payload).model_dump()
        person = self.dependencies.base_record("parties", data["person_uid"])
        if person["kind"] != "person":
            raise PeopleError(422, "person", "Employee must reference a Base person")
        data["name"] = person["name"]
        data["company_name"] = self.company(data["operating_company_uid"])["name"]
        data["department_name"] = ""
        if data["department_uid"]:
            department = self.row("departments", data["department_uid"])
            self.active(department)
            if department["operating_company_uid"] != str(data["operating_company_uid"]):
                raise PeopleError(422, "department", "Choose a department in the employing company")
            data["department_name"] = department["name"]
        old = self.row("employees", uid) if uid else None
        if old:
            self.active(old)
            if any(str(data[k]) != old[k] for k in ("person_uid", "operating_company_uid")):
                raise PeopleError(422, "identity", "Employee person and company cannot change")
            outside = [AbsenceRequest.start_date < data["start_date"]]
            if data["end_date"]:
                outside.append(AbsenceRequest.end_date > data["end_date"])
            if self.count(
                AbsenceRequest,
                AbsenceRequest.employee_uid == key(uid),
                AbsenceRequest.state.in_(["submitted", "approved"]),
                or_(*outside),
            ):
                raise PeopleError(
                    409,
                    "absence_dates",
                    "Employment dates must include submitted and approved absences",
                )
            steps = [self.guard("employees", old, expected_version, data)]
            version = expected_version + 1
        else:
            uid, version = request_uid or uuid4(), 1
            steps = [
                insert(Employee).values(uid=key(uid), **data, **self.created(), state="active")
            ]
        steps += self.membership_steps(
            old["department_uid"] if old else None, data["department_uid"]
        )
        self.transact(
            [
                *steps,
                self.audit(
                    "employees", uid, "update" if expected_version else "create", version, data
                ),
            ]
        )
        return self.get("employees", uid)

    def archive(self, resource, uid, action, expected_version):
        self.require("people.manage")
        if resource not in {"employees", "departments"} or action not in {"archive", "restore"}:
            raise PeopleError(404, "action", "Unknown workforce action")
        row = self.row(resource, uid)
        target = "archived" if action == "archive" else "active"
        if row["state"] == target:
            raise PeopleError(409, "state", "Record is already in this state")
        steps = []
        if target == "active":
            self.company(row["operating_company_uid"])
        if (
            resource == "departments"
            and target == "archived"
            and self.count(
                Employee, Employee.department_uid == key(uid), Employee.state == "active"
            )
        ):
            raise PeopleError(
                409,
                "active_members",
                "Move or archive active employees before archiving the department",
            )
        if resource == "employees":
            if target == "archived" and self.count(
                AbsenceRequest,
                AbsenceRequest.employee_uid == key(uid),
                or_(
                    AbsenceRequest.state == "submitted",
                    (AbsenceRequest.state == "approved")
                    & (AbsenceRequest.end_date >= date.today()),
                ),
            ):
                raise PeopleError(
                    409,
                    "open_absence",
                    "Resolve submitted or current/future approved absences before archiving",
                )
            if target == "active":
                self.dependencies.base_record("parties", row["person_uid"])
            steps += self.membership_steps(
                row["department_uid"], row["department_uid"] if target == "active" else None
            )
        self.transact(
            [
                *steps,
                self.guard(resource, row, expected_version, {"state": target}),
                self.audit(resource, uid, action, expected_version + 1, ["state"]),
            ]
        )
        return self.get(resource, uid)

    def absence_context(self, employee_uid, start, end):
        employee = self.row("employees", employee_uid)
        self.active(employee)
        if (
            day(start) < day(employee["start_date"])
            or employee["end_date"]
            and day(end) > day(employee["end_date"])
        ):
            raise PeopleError(422, "employment_dates", "Absence must fall within employment dates")
        return employee

    def save_absence(
        self,
        payload,
        *,
        expected_employee_version,
        uid=None,
        expected_version=None,
        request_uid=None,
    ):
        self.require("people.write")
        data = AbsenceInput.model_validate(payload).model_dump()
        employee = self.absence_context(data["employee_uid"], data["start_date"], data["end_date"])
        data["employee_name"] = employee["name"]
        if uid:
            old = self.row("absences", uid)
            if old["state"] != "draft":
                raise PeopleError(409, "frozen", "Only draft absence requests can be edited")
            if str(data["employee_uid"]) != old["employee_uid"]:
                raise PeopleError(422, "employee", "Request employee cannot change")
            steps = [self.guard("absences", old, expected_version, data)]
            version = expected_version + 1
        else:
            uid, version = request_uid or uuid4(), 1
            steps = [
                insert(AbsenceRequest).values(
                    uid=key(uid),
                    **data,
                    **self.created(),
                    state="draft",
                    decision_by_uid=None,
                    decision_at=None,
                    decision_note="",
                    cancellation_reason="",
                )
            ]
        self.transact(
            [
                self.guard("employees", employee, expected_employee_version, {}),
                *steps,
                self.audit(
                    "absences", uid, "update" if expected_version else "create", version, data
                ),
                self.audit(
                    "employees",
                    employee["uid"],
                    "absence-change",
                    expected_employee_version + 1,
                    ["absences"],
                ),
            ]
        )
        return self.get("absences", uid)

    def absence_action(self, uid, action, payload):
        self.require("people.manage" if action in {"approve", "reject"} else "people.write")
        row = self.row("absences", uid)
        transitions = {
            "submit": ({"draft"}, "submitted"),
            "approve": ({"submitted"}, "approved"),
            "reject": ({"submitted"}, "rejected"),
            "cancel": ({"draft", "submitted", "approved"}, "cancelled"),
        }
        if action not in transitions or row["state"] not in transitions[action][0]:
            raise PeopleError(409, "state", "Absence action is unavailable in this state")
        if row["state"] == "approved":
            self.require("people.manage")
        if action in {"approve", "reject"} and row["created_by_uid"] == str(self.actor_uid):
            raise PeopleError(
                403, "self_approval", "A different authorized person must decide this request"
            )
        note = payload.get("note", "").strip()
        if action in {"reject", "cancel"} and not note:
            raise PeopleError(422, "reason", "Enter a reason for rejection or cancellation")
        employee = self.row("employees", row["employee_uid"])
        if action in {"submit", "approve"}:
            self.absence_context(employee["uid"], row["start_date"], row["end_date"])
            if self.count(
                AbsenceRequest,
                AbsenceRequest.employee_uid == key(employee["uid"]),
                AbsenceRequest.uid != key(uid),
                AbsenceRequest.state.in_(["submitted", "approved"]),
                AbsenceRequest.start_date <= day(row["end_date"]),
                AbsenceRequest.end_date >= day(row["start_date"]),
            ):
                raise PeopleError(
                    409, "overlap", "This absence overlaps a submitted or approved request"
                )
        data = {"state": transitions[action][1]}
        if action in {"approve", "reject"}:
            data.update(decision_by_uid=self.actor_uid, decision_at=now(), decision_note=note)
        elif action == "cancel":
            data["cancellation_reason"] = note
        ev, rv = payload["expected_employee_version"], payload["expected_version"]
        self.transact(
            [
                self.guard("employees", employee, ev, {}),
                self.guard("absences", row, rv, data),
                self.audit("employees", employee["uid"], "absence-" + action, ev + 1, ["absences"]),
                self.audit("absences", uid, action, rv + 1, data),
            ]
        )
        return self.get("absences", uid)

    def staff(self, uid, payload):
        self.require("people.manage")
        data = StaffInput.model_validate(payload).model_dump()
        employee = self.row("employees", uid)
        self.active(employee)
        if (
            day(employee["start_date"]) > date.today()
            or employee["end_date"]
            and day(employee["end_date"]) < date.today()
        ):
            raise PeopleError(409, "employment_dates", "Staffing requires current employment")
        projects = self.dependencies.projects()
        if projects.store.data_source_uid != self.store.data_source_uid:
            raise PeopleError(409, "source", "Atomic staffing requires a shared DataSource")
        task, steps = projects.plan_assignment(
            data["task_uid"],
            person_uid=employee["person_uid"],
            operating_company_uid=employee["operating_company_uid"],
            expected_version=data["expected_task_version"],
            expected_project_version=data["expected_project_version"],
        )
        self.transact(
            [
                self.guard("employees", employee, data["expected_version"], {}),
                *steps,
                self.audit(
                    "employees",
                    uid,
                    "staff-project-task",
                    data["expected_version"] + 1,
                    ["staffing"],
                    {
                        "task_uid": str(data["task_uid"]),
                        "task_version": data["expected_task_version"] + 1,
                    },
                ),
            ]
        )
        return {"employee": self.get("employees", uid), "task": projects.get("tasks", task["uid"])}
