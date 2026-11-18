"""Version-fenced delivery aggregates and explicit owner-composed handoffs."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, insert, or_, select, update

from mainsequence.client.exceptions import BadRequestError
from metatables import MetaTableTransactionGuardError
from metatables.compiled_sql.v1 import GuardedStatement
from src.erp.module_access import require_module

from .errors import ProjectsError
from .metatables import RESOURCES, AuditEvent, DeliveryTask, Project, TimeEntry
from .schemas import BillInput, FromSales, ProjectInput, TaskInput, TimeInput, VoidTime


def now():
    return datetime.now(timezone.utc)


def key(value):
    return UUID(str(value))


def page(items, total, index, size):
    return {
        "items": items,
        "pageInfo": {
            "pageIndex": index,
            "pageSize": size,
            "totalItems": total,
            "hasNextPage": (index + 1) * size < total,
            "hasPreviousPage": index > 0,
        },
    }


class Service:
    def __init__(self, store, actor_uid, capabilities, dependencies):
        self.store, self.actor_uid, self.capabilities, self.dependencies = (
            store,
            key(actor_uid),
            set(capabilities),
            dependencies,
        )

    def require(self, cap):
        require_module("projects")
        if cap not in self.capabilities:
            raise ProjectsError(403, "forbidden", "Projects access does not permit this operation")

    def row(self, resource, uid):
        self.require("projects.read")
        if resource not in RESOURCES:
            raise ProjectsError(404, "not_found", "Unknown delivery resource")
        model = RESOURCES[resource]
        rows = self.store.read(select(model.__table__).where(model.uid == key(uid)).limit(1))
        if not rows:
            raise ProjectsError(404, "not_found", "Delivery record not found")
        return rows[0]

    def get(self, resource, uid):
        row = self.row(resource, uid)
        if resource == "projects":
            states = self.store.read(
                select(DeliveryTask.state, func.count().label("count"))
                .where(DeliveryTask.project_uid == key(uid))
                .group_by(DeliveryTask.state)
            )
            row["task_counts"] = {item["state"]: item["count"] for item in states}
            row["recorded_minutes"] = int(
                self.store.read(
                    select(func.coalesce(func.sum(TimeEntry.minutes), 0).label("minutes"))
                    .join(DeliveryTask, DeliveryTask.uid == TimeEntry.task_uid)
                    .where(DeliveryTask.project_uid == key(uid), TimeEntry.state == "recorded")
                )[0]["minutes"]
            )
        elif resource == "tasks":
            project = self.row("projects", row["project_uid"])
            row["project_name"] = project["name"]
            row["project_version"] = project["version"]
            row["project_state"] = project["state"]
            row["recorded_minutes"] = int(
                self.store.read(
                    select(func.coalesce(func.sum(TimeEntry.minutes), 0).label("minutes")).where(
                        TimeEntry.task_uid == key(uid), TimeEntry.state == "recorded"
                    )
                )[0]["minutes"]
            )
        return row

    def collection(
        self, resource, *, page_index=0, page_size=25, search="", state=None, project_uid=None
    ):
        self.require("projects.read")
        if resource not in {"projects", "tasks"}:
            raise ProjectsError(404, "not_found", "Unknown delivery collection")
        model = RESOURCES[resource]
        terms = []
        if search:
            terms.append(
                or_(
                    func.lower(model.name).contains(search.lower(), autoescape=True),
                    func.lower(model.description).contains(search.lower(), autoescape=True),
                )
            )
        if state:
            terms.append(model.state == state)
        if project_uid:
            if resource != "tasks":
                raise ProjectsError(422, "filter", "Project filter is only available for tasks")
            self.row("projects", project_uid)
            terms.append(model.project_uid == key(project_uid))
        total = int(
            self.store.read(select(func.count().label("count")).select_from(model).where(*terms))[
                0
            ]["count"]
        )
        items = self.store.read(
            select(model.__table__)
            .where(*terms)
            .order_by(model.created_at.desc(), model.uid)
            .offset(page_index * page_size)
            .limit(page_size),
            max_rows=page_size,
        )
        return page(items, total, page_index, page_size)

    def history(self, task_uid, *, page_index=0, page_size=25):
        self.row("tasks", task_uid)
        terms = [TimeEntry.task_uid == key(task_uid)]
        total = int(
            self.store.read(
                select(func.count().label("count")).select_from(TimeEntry).where(*terms)
            )[0]["count"]
        )
        items = self.store.read(
            select(TimeEntry.__table__)
            .where(*terms)
            .order_by(TimeEntry.created_at.desc(), TimeEntry.uid)
            .offset(page_index * page_size)
            .limit(page_size),
            max_rows=page_size,
        )
        return page(items, total, page_index, page_size)

    def transact(self, steps):
        try:
            return self.store.write(steps)
        except MetaTableTransactionGuardError as exc:
            raise ProjectsError(
                409, "conflict", "Project or delivery record changed; reload and review"
            ) from exc
        except BadRequestError as exc:
            detail = (getattr(exc, "payload", {}) or {}).get("detail", {})
            if isinstance(detail, dict) and detail.get("code") == "compiled_sql_database_error":
                raise ProjectsError(
                    409,
                    "constraint_conflict",
                    "Reference, source or request already exists; check the saved record",
                ) from exc
            raise

    def audit(self, resource, uid, action, version, fields):
        return insert(AuditEvent).values(
            uid=uuid4(),
            resource=resource,
            record_uid=key(uid),
            action=action,
            version=version,
            actor_uid=self.actor_uid,
            occurred_at=now(),
            fields=sorted(fields),
        )

    def created(self):
        return dict(
            version=1,
            created_at=now(),
            updated_at=now(),
            created_by_uid=self.actor_uid,
            updated_by_uid=self.actor_uid,
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

    def editable_project(self, project):
        if project["state"] not in {"planned", "active"}:
            raise ProjectsError(
                409,
                "project_frozen",
                "Reopen an unbilled delivered project before changing delivery",
            )

    def references(self, data):
        party = self.dependencies.base_record("parties", data["customer_uid"])
        company = self.dependencies.base_record(
            "operating-companies", data["operating_company_uid"]
        )
        self.dependencies.base_record("parties", company["party_uid"])
        return {"customer_name": party["name"], "company_name": company["name"]}

    def assignee(self, uid):
        if uid is None:
            return ""
        person = self.dependencies.base_record("parties", uid)
        if person["kind"] != "person":
            raise ProjectsError(422, "assignee", "Task assignee must be a person")
        return person["name"]

    def save_project(self, payload, *, uid=None, expected_version=None, request_uid=None):
        self.require("projects.write")
        data = ProjectInput.model_validate(payload).model_dump()
        data.update(self.references(data))
        if uid:
            old = self.row("projects", uid)
            self.editable_project(old)
            if old["source_order_uid"] and any(
                str(data[k]) != str(old[k]) for k in ("customer_uid", "operating_company_uid")
            ):
                raise ProjectsError(
                    422, "source_terms", "Source order customer and company cannot change"
                )
            steps = [self.guard("projects", old, expected_version, data)]
            version = expected_version + 1
        else:
            uid = request_uid or uuid4()
            version = 1
            steps = [
                insert(Project).values(
                    uid=key(uid),
                    **data,
                    **self.created(),
                    state="planned",
                    source_order_uid=None,
                    source_order_name=None,
                    source_snapshot={},
                    invoice_uid=None,
                    invoice_name=None,
                )
            ]
        self.transact(
            [
                *steps,
                self.audit(
                    "projects", uid, "update" if expected_version else "create", version, data
                ),
            ]
        )
        return self.get("projects", uid)

    def save_task(
        self,
        payload,
        *,
        expected_project_version,
        uid=None,
        expected_version=None,
        request_uid=None,
    ):
        self.require("projects.write")
        data = TaskInput.model_validate(payload).model_dump()
        project = self.row("projects", data["project_uid"])
        self.editable_project(project)
        data["assignee_name"] = self.assignee(data["assignee_party_uid"])
        steps = [self.guard("projects", project, expected_project_version, {})]
        if uid:
            old = self.row("tasks", uid)
            if str(data["project_uid"]) != old["project_uid"]:
                raise ProjectsError(422, "project", "Task cannot change projects")
            if old["state"] in {"done", "cancelled"}:
                raise ProjectsError(409, "task_frozen", "Reopen the task before editing")
            version = expected_version + 1
            steps.append(self.guard("tasks", old, expected_version, data))
        else:
            uid = request_uid or uuid4()
            version = 1
            steps.append(
                insert(DeliveryTask).values(
                    uid=key(uid), **data, **self.created(), state="todo", source_line_uid=None
                )
            )
        self.transact(
            [
                *steps,
                self.audit("tasks", uid, "update" if expected_version else "create", version, data),
                self.audit(
                    "projects",
                    project["uid"],
                    "task-change",
                    expected_project_version + 1,
                    ["tasks"],
                ),
            ]
        )
        return self.get("tasks", uid)

    def plan_assignment(
        self, uid, *, person_uid, operating_company_uid, expected_version, expected_project_version
    ):
        """Public owner command plan for authorized same-source workforce staffing."""
        self.require("projects.write")
        task = self.row("tasks", uid)
        project = self.row("projects", task["project_uid"])
        self.editable_project(project)
        if project["operating_company_uid"] != str(operating_company_uid):
            raise ProjectsError(422, "company", "Employee and project must use the same company")
        if task["state"] in {"done", "cancelled"}:
            raise ProjectsError(409, "task_frozen", "Reopen the task before staffing")
        self.references(project)
        data = {"assignee_party_uid": key(person_uid), "assignee_name": self.assignee(person_uid)}
        return task, [
            self.guard("projects", project, expected_project_version, {}),
            self.guard("tasks", task, expected_version, data),
            self.audit("tasks", uid, "staff", expected_version + 1, data),
            self.audit(
                "projects", project["uid"], "task-staff", expected_project_version + 1, ["tasks"]
            ),
        ]

    def task_state(self, uid, state, expected_version, expected_project_version):
        self.require("projects.write")
        task = self.row("tasks", uid)
        project = self.row("projects", task["project_uid"])
        self.editable_project(project)
        if state not in {"todo", "in_progress", "blocked", "done", "cancelled"}:
            raise ProjectsError(422, "state", "Unknown task state")
        if state == task["state"] or task["state"] in {"done", "cancelled"} and state != "todo":
            raise ProjectsError(409, "state", "Completed or cancelled tasks must reopen to To do")
        if state == "done" and project["state"] != "active":
            raise ProjectsError(
                409, "project_state", "Start the project before completing delivery"
            )
        self.transact(
            [
                self.guard("projects", project, expected_project_version, {}),
                self.guard("tasks", task, expected_version, {"state": state}),
                self.audit("tasks", uid, "state", expected_version + 1, ["state"]),
                self.audit(
                    "projects",
                    project["uid"],
                    "task-state",
                    expected_project_version + 1,
                    ["tasks"],
                ),
            ]
        )
        return self.get("tasks", uid)

    def transition(self, uid, action, expected_version):
        self.require("projects.manage")
        project = self.row("projects", uid)
        transitions = {
            "start": ({"planned"}, "active"),
            "deliver": ({"active"}, "delivered"),
            "close": ({"delivered"}, "closed"),
            "reopen": ({"delivered"}, "active"),
            "cancel": ({"planned", "active"}, "cancelled"),
        }
        if action not in transitions or project["state"] not in transitions[action][0]:
            raise ProjectsError(409, "state", "Project action is unavailable in this state")
        if project["invoice_uid"]:
            raise ProjectsError(409, "billed", "Billed delivery is immutable")
        if action in {"start", "deliver"}:
            self.references(project)
        if action in {"deliver", "cancel"}:
            counts = self.get("projects", uid)["task_counts"]
            if any(count for state, count in counts.items() if state not in {"done", "cancelled"}):
                raise ProjectsError(409, "open_tasks", "Finish or cancel open delivery tasks first")
            if action == "deliver" and not counts.get("done"):
                raise ProjectsError(409, "empty_delivery", "At least one task must be completed")
        self.transact(
            [
                self.guard(
                    "projects", project, expected_version, {"state": transitions[action][1]}
                ),
                self.audit("projects", uid, action, expected_version + 1, ["state"]),
            ]
        )
        return self.get("projects", uid)

    def time_context(self, task_uid):
        task = self.row("tasks", task_uid)
        project = self.row("projects", task["project_uid"])
        if project["state"] != "active" or task["state"] == "cancelled":
            raise ProjectsError(
                409,
                "effort_frozen",
                "Effort can change only on an active project and a task that is not cancelled",
            )
        return task, project

    def log_time(self, task_uid, payload):
        self.require("projects.write")
        data = TimeInput.model_validate(payload)
        task, project = self.time_context(task_uid)
        if data.work_date > now().date():
            raise ProjectsError(422, "future_date", "Work date cannot be in the future")
        values = data.model_dump(
            exclude={"request_uid", "expected_task_version", "expected_project_version"}
        )
        self.transact(
            [
                self.guard("projects", project, data.expected_project_version, {}),
                self.guard("tasks", task, data.expected_task_version, {}),
                insert(TimeEntry).values(
                    uid=data.request_uid,
                    task_uid=key(task_uid),
                    **values,
                    **self.created(),
                    state="recorded",
                    void_reason="",
                ),
                self.audit("time-entries", data.request_uid, "record", 1, values),
                self.audit(
                    "tasks",
                    task_uid,
                    "effort",
                    data.expected_task_version + 1,
                    ["recorded_minutes"],
                ),
                self.audit(
                    "projects",
                    project["uid"],
                    "effort",
                    data.expected_project_version + 1,
                    ["recorded_minutes"],
                ),
            ]
        )
        return {
            "entry": self.row("time-entries", data.request_uid),
            "task": self.get("tasks", task_uid),
        }

    def void_time(self, uid, payload):
        self.require("projects.write")
        data = VoidTime.model_validate(payload)
        entry = self.row("time-entries", uid)
        if entry["created_by_uid"] != str(self.actor_uid):
            self.require("projects.manage")
        if entry["state"] != "recorded":
            raise ProjectsError(409, "voided", "Effort entry is already voided")
        task, project = self.time_context(entry["task_uid"])
        self.transact(
            [
                self.guard("projects", project, data.expected_project_version, {}),
                self.guard("tasks", task, data.expected_task_version, {}),
                self.guard(
                    "time-entries",
                    entry,
                    data.expected_version,
                    {"state": "voided", "void_reason": data.reason},
                ),
                self.audit(
                    "time-entries", uid, "void", data.expected_version + 1, ["state", "void_reason"]
                ),
                self.audit(
                    "tasks",
                    task["uid"],
                    "effort-void",
                    data.expected_task_version + 1,
                    ["recorded_minutes"],
                ),
                self.audit(
                    "projects",
                    project["uid"],
                    "effort-void",
                    data.expected_project_version + 1,
                    ["recorded_minutes"],
                ),
            ]
        )
        return {"entry": self.row("time-entries", uid), "task": self.get("tasks", task["uid"])}

    def same_source(self, owner):
        if str(owner.store.data_source_uid) != str(self.store.data_source_uid):
            raise ProjectsError(
                503, "integration_source", "Atomic handoff requires the same governed DataSource"
            )

    def from_sales(self, payload):
        self.require("projects.manage")
        data = FromSales.model_validate(payload)
        sales = self.dependencies.sales()
        self.same_source(sales)
        order = sales.service_order(data.order_uid)
        if order["state"] != "confirmed" or order["version"] != data.expected_order_version:
            raise ProjectsError(409, "source_changed", "Choose the current confirmed service order")
        values = {
            "name": data.name,
            "description": order["notes"],
            "customer_uid": key(order["customer_uid"]),
            "operating_company_uid": key(order["operating_company_uid"]),
            "start_date": None,
            "due_date": data.due_date,
        }
        values.update(self.references(values))
        tasks = [
            {
                "uid": uuid4(),
                "project_uid": data.request_uid,
                "name": line["description"][:200] or line["snapshot"]["item_name"][:200],
                "description": line["description"],
                "state": "todo",
                "assignee_party_uid": None,
                "assignee_name": "",
                "due_date": data.due_date,
                "estimate_minutes": 0,
                "source_line_uid": key(line["uid"]),
                **self.created(),
            }
            for line in order["lines"]
        ]
        plan = sales.plan_attach(
            data.order_uid, data.expected_order_version, "projects", data.request_uid
        )
        self.transact(
            [
                *plan,
                insert(Project).values(
                    uid=data.request_uid,
                    **values,
                    **self.created(),
                    state="planned",
                    source_order_uid=data.order_uid,
                    source_order_name=order["name"],
                    source_snapshot=order,
                    invoice_uid=None,
                    invoice_name=None,
                ),
                insert(DeliveryTask).values(tasks),
                insert(AuditEvent).values(
                    [
                        dict(
                            uid=uuid4(),
                            resource="tasks",
                            record_uid=task["uid"],
                            action="from-sales",
                            version=1,
                            actor_uid=self.actor_uid,
                            occurred_at=now(),
                            fields=sorted(task),
                        )
                        for task in tasks
                    ]
                ),
                self.audit(
                    "projects", data.request_uid, "from-sales", 1, ["source_order_uid", "tasks"]
                ),
            ]
        )
        return self.get("projects", data.request_uid)

    def bill(self, uid, payload):
        self.require("projects.manage")
        data = BillInput.model_validate(payload)
        project = self.row("projects", uid)
        if (
            project["state"] != "delivered"
            or not project["source_order_uid"]
            or project["invoice_uid"]
        ):
            raise ProjectsError(
                409, "billing_state", "Deliver a source service-order project before billing"
            )
        finance = self.dependencies.finance()
        self.same_source(finance)
        plan = finance.plan_invoice(
            project["source_order_uid"], data.model_dump(exclude={"expected_version"})
        )
        self.transact(
            [
                self.guard(
                    "projects",
                    project,
                    data.expected_version,
                    {"state": "closed", "invoice_uid": data.request_uid, "invoice_name": data.name},
                ),
                *plan,
                self.audit(
                    "projects",
                    uid,
                    "bill",
                    data.expected_version + 1,
                    ["invoice_uid", "invoice_name", "state"],
                ),
            ]
        )
        return self.get("projects", uid)
