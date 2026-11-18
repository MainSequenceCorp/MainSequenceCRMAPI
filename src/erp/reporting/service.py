"""Private reports and durable one-step-at-a-time refresh automation."""

import csv
import io
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4, uuid5

from sqlalchemy import func, insert, select, update

from mainsequence.client.exceptions import BadRequestError
from metatables import MetaTableTransactionGuardError
from metatables.compiled_sql.v1 import GuardedStatement
from src.erp.module_access import require_module

from .errors import ReportingError
from .metatables import RESOURCES, AuditEvent, Definition, Run, RunStep, Schedule
from .schemas import DefinitionInput, RunCreate, ScheduleInput
from .sources import KINDS, summarize


def key(value):
    return UUID(str(value))


def now():
    return datetime.now(timezone.utc)


def timestamp(value):
    value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class Service:
    def __init__(self, store, actor_uid, capabilities, sources):
        self.store, self.actor_uid, self.capabilities, self.sources = (
            store,
            key(actor_uid),
            set(capabilities),
            sources,
        )

    def require(self, cap):
        require_module("reporting")
        if cap not in self.capabilities:
            raise ReportingError(
                403, "forbidden", "Reporting access does not permit this operation"
            )

    def created(self):
        return dict(
            version=1,
            created_at=now(),
            updated_at=now(),
            created_by_uid=self.actor_uid,
            updated_by_uid=self.actor_uid,
        )

    def raw(self, resource, uid):
        self.require("reporting.read")
        model = RESOURCES.get(resource)
        if model is None:
            raise ReportingError(404, "not_found", "Unknown reporting collection")
        rows = self.store.read(
            select(model.__table__)
            .where(model.uid == key(uid), model.created_by_uid == self.actor_uid)
            .limit(1)
        )
        if not rows:
            raise ReportingError(404, "not_found", "Reporting record not found")
        return rows[0]

    def safe(self, resource, row):
        row = dict(row)
        if resource == "runs":
            row.pop("lease_uid", None)
            row.pop("summary", None)
            row["step_count"] = len(KINDS[row["config"]["kind"]])
            row["recoverable"] = (
                row["state"] == "running"
                and row["lease_until"] is not None
                and timestamp(row["lease_until"]) <= now()
            )
        return row

    def steps(self, uid):
        return self.store.read(
            select(RunStep.__table__)
            .where(RunStep.run_uid == key(uid), RunStep.created_by_uid == self.actor_uid)
            .order_by(RunStep.position)
            .limit(4)
        )

    def get(self, resource, uid):
        row = self.safe(resource, self.raw(resource, uid))
        if resource == "runs":
            row["steps"] = [{k: v for k, v in x.items() if k != "records"} for x in self.steps(uid)]
        if resource == "schedules":
            row["definition_name"] = self.raw("definitions", row["definition_uid"])["name"]
        return row

    def collection(self, resource, *, page_index=0, page_size=25, search="", state=None):
        self.require("reporting.read")
        model = RESOURCES.get(resource)
        if model is None:
            raise ReportingError(404, "not_found", "Unknown reporting collection")
        terms = [model.created_by_uid == self.actor_uid]
        if search:
            terms.append(func.lower(model.name).contains(search.lower(), autoescape=True))
        if state:
            terms.append(model.state == state)
        count = int(
            self.store.read(select(func.count().label("count")).select_from(model).where(*terms))[
                0
            ]["count"]
        )
        rows = self.store.read(
            select(model.__table__)
            .where(*terms)
            .order_by(model.created_at.desc(), model.uid)
            .offset(page_index * page_size)
            .limit(page_size),
            max_rows=page_size,
        )
        return page([self.safe(resource, r) for r in rows], count, page_index, page_size)

    def guard(self, model, row, expected, changes=None, *, extra=(), bump=True):
        if row["version"] != expected:
            raise ReportingError(409, "conflict", "Record changed; reload and review")
        values = dict(changes or {})
        if bump:
            values.update(version=expected + 1, updated_at=now(), updated_by_uid=self.actor_uid)
        else:
            values.update(updated_at=model.updated_at)
        return GuardedStatement(
            update(model)
            .where(
                model.uid == key(row["uid"]),
                model.version == expected,
                model.state == row["state"],
                model.created_by_uid == self.actor_uid,
                *extra,
            )
            .values(**values)
            .returning(model.uid),
            expect_rows=1,
            label="reporting_version",
        )

    def audit(self, resource, uid, action, version, fields):
        return insert(AuditEvent).values(
            uid=uuid4(),
            resource=resource,
            record_uid=key(uid),
            actor_uid=self.actor_uid,
            action=action,
            version=version,
            occurred_at=now(),
            fields=list(fields),
        )

    def transact(self, steps):
        try:
            return self.store.write(steps)
        except MetaTableTransactionGuardError as e:
            raise ReportingError(
                409, "conflict", "Record or worker claim changed; reload before continuing"
            ) from e
        except BadRequestError as e:
            detail = (getattr(e, "payload", {}) or {}).get("detail", {})
            if isinstance(detail, dict) and detail.get("code") == "compiled_sql_database_error":
                raise ReportingError(
                    409,
                    "constraint_conflict",
                    "This name or request already exists; check the saved record",
                ) from e
            raise

    def save(self, resource, payload, *, uid=None, request_uid=None, expected_version=None):
        if resource not in {"definitions", "schedules"}:
            raise ReportingError(404, "not_found", "This collection cannot be edited")
        self.require("reporting.write" if resource == "definitions" else "reporting.manage")
        data = (DefinitionInput if resource == "definitions" else ScheduleInput).model_validate(
            payload
        )
        values = data.model_dump()
        row = self.raw(resource, uid) if uid else None
        if row and row["state"] != ("active" if resource == "definitions" else "paused"):
            raise ReportingError(
                409, "state", "Restore the report or pause the schedule before editing"
            )
        plan = []
        if resource == "schedules":
            definition = self.raw("definitions", data.definition_uid)
            if definition["state"] != "active":
                raise ReportingError(409, "archived", "Choose an active saved report")
            plan.append(self.guard(Definition, definition, definition["version"], bump=False))
        uid = key(uid or request_uid)
        if row:
            if resource == "schedules":
                values["last_error"] = ""
            plan.append(self.guard(RESOURCES[resource], row, expected_version, values))
            version = expected_version + 1
        else:
            values.update(
                state="active" if resource == "definitions" else "paused", **self.created()
            )
            if resource == "schedules":
                values.update(next_run_at=None, last_run_uid=None, last_error="")
            plan.append(insert(RESOURCES[resource]).values(uid=uid, **values))
            version = 1
        self.transact(
            [*plan, self.audit(resource, uid, "update" if row else "create", version, values)]
        )
        return self.get(resource, uid)

    def definition_state(self, uid, action, expected):
        self.require("reporting.write")
        row = self.raw("definitions", uid)
        before, after = ("active", "archived") if action == "archive" else ("archived", "active")
        if row["state"] != before:
            raise ReportingError(409, "state", "Report is not in the required state")
        self.transact(
            [
                self.guard(Definition, row, expected, {"state": after}),
                self.audit("definitions", uid, action, expected + 1, ["state"]),
            ]
        )
        return self.get("definitions", uid)

    def run_plan(self, definition, uid, *, schedule=None, due=None):
        config = {k: definition[k] for k in ["kind", "search", "version"]}
        values = dict(
            uid=key(uid),
            name=definition["name"],
            definition_uid=key(definition["uid"]),
            schedule_uid=key(schedule["uid"]) if schedule else None,
            scheduled_for=due,
            state="queued",
            config=config,
            progress=0,
            lease_uid=None,
            lease_until=None,
            summary={},
            error="",
            finished_at=None,
            **self.created(),
        )
        steps = [
            dict(
                uid=uuid5(key(uid), source),
                run_uid=key(uid),
                position=i + 1,
                source=source,
                state="pending",
                attempts=0,
                captured_at=None,
                records=[],
                error="",
                **self.created(),
            )
            for i, source in enumerate(KINDS[config["kind"]])
        ]
        return [
            self.guard(Definition, definition, definition["version"], bump=False),
            insert(Run).values(**values),
            insert(RunStep).values(steps),
            self.audit("runs", uid, "schedule" if schedule else "queue", 1, ["config", "state"]),
        ]

    def queue(self, payload):
        self.require("reporting.run")
        data = RunCreate.model_validate(payload)
        definition = self.raw("definitions", data.definition_uid)
        if (
            definition["state"] != "active"
            or definition["version"] != data.expected_definition_version
        ):
            raise ReportingError(
                409, "definition_changed", "Reload the active saved report before queuing a run"
            )
        self.transact(self.run_plan(definition, data.request_uid))
        return self.get("runs", data.request_uid)

    def claim(self, uid, expected):
        self.require("reporting.run")
        row = self.raw("runs", uid)
        if row["state"] not in {"queued", "running"} or row["lease_uid"]:
            raise ReportingError(
                409, "state", "Run cannot advance; inspect progress or recover an expired claim"
            )
        steps = self.steps(uid)
        step = next((s for s in steps if s["state"] == "pending"), None)
        if not step:
            raise ReportingError(409, "state", "No pending source step remains")
        lease = uuid4()
        until = now() + timedelta(minutes=2)
        self.transact(
            [
                self.guard(
                    Run,
                    row,
                    expected,
                    {
                        "state": "running",
                        "lease_uid": lease,
                        "lease_until": until,
                        "error": "",
                        "finished_at": None,
                    },
                ),
                self.guard(
                    RunStep,
                    step,
                    step["version"],
                    {"state": "running", "attempts": step["attempts"] + 1, "error": ""},
                ),
                self.audit("runs", uid, "claim", expected + 1, ["state", "lease_until"]),
            ]
        )
        return (
            {
                **row,
                "state": "running",
                "version": expected + 1,
                "lease_uid": str(lease),
                "lease_until": until,
            },
            {
                **step,
                "state": "running",
                "version": step["version"] + 1,
                "attempts": step["attempts"] + 1,
            },
        )

    def finish(self, row, step, records=None, error=""):
        valid = [Run.lease_uid == key(row["lease_uid"]), Run.lease_until > now()]
        changes = {"lease_uid": None, "lease_until": None}
        if error:
            changes.update(state="failed", error=error, finished_at=now())
            step_values = {"state": "failed", "error": error}
        else:
            progress = row["progress"] + 1
            complete = progress == len(KINDS[row["config"]["kind"]])
            changes.update(
                state="succeeded" if complete else "running",
                progress=progress,
                error="",
                finished_at=now() if complete else None,
            )
            if complete:
                previous = [
                    r for s in self.steps(row["uid"]) if s["state"] == "done" for r in s["records"]
                ]
                changes["summary"] = summarize(row["config"]["kind"], previous + records)
            step_values = {"state": "done", "records": records, "captured_at": now(), "error": ""}
        self.transact(
            [
                self.guard(Run, row, row["version"], changes, extra=valid),
                self.guard(RunStep, step, step["version"], step_values),
                self.audit(
                    "runs",
                    row["uid"],
                    "fail" if error else "capture",
                    row["version"] + 1,
                    ["state", "progress", "summary"] if not error else ["state", "error"],
                ),
            ]
        )
        return self.get("runs", row["uid"])

    def advance(self, uid, expected):
        row, step = self.claim(uid, expected)
        try:
            records = self.sources.capture(
                step["source"], row["config"]["search"], self.store.data_source_uid
            )
        except ReportingError as e:
            safe = {
                "source_limit": "source_limit: Narrow the saved search and create a new run.",
                "source_changed": "source_changed: Retry this step after source edits settle.",
                "source_disabled": "source_disabled: Enable the source module, then retry.",
                "module_disabled": "source_disabled: Activate the source module, then retry.",
                "source_mismatch": "source_mismatch: Correct the source configuration before retrying.",
            }.get(
                e.code,
                "source_access: Verify the source is available and your read access, then retry.",
            )
            return self.finish(row, step, error=safe)
        except Exception:
            return self.finish(
                row,
                step,
                error="source_unavailable: Source read failed; inspect service readiness before retrying.",
            )
        return self.finish(row, step, records)

    def control(self, uid, action, expected):
        self.require("reporting.run")
        row = self.raw("runs", uid)
        steps = self.steps(uid)
        plan = []
        if action == "cancel":
            if row["state"] not in {"queued", "running", "failed"}:
                raise ReportingError(409, "state", "This run cannot be cancelled")
            selected = [s for s in steps if s["state"] in {"pending", "running", "failed"}]
            step_state, state = "cancelled", "cancelled"
            finished = now()
        elif action == "retry":
            if row["state"] != "failed":
                raise ReportingError(409, "state", "Only a failed run can retry")
            selected = [s for s in steps if s["state"] == "failed"]
            step_state, state = "pending", "queued"
            finished = None
        elif action == "recover":
            if (
                row["state"] != "running"
                or not row["lease_until"]
                or timestamp(row["lease_until"]) > now()
            ):
                raise ReportingError(
                    409, "lease_active", "Recovery requires an expired worker claim"
                )
            selected = [s for s in steps if s["state"] == "running"]
            step_state, state = "pending", "queued"
            finished = None
        else:
            raise ReportingError(404, "not_found", "Unknown run action")
        for step in selected:
            plan.append(
                self.guard(RunStep, step, step["version"], {"state": step_state, "error": ""})
            )
        self.transact(
            [
                self.guard(
                    Run,
                    row,
                    expected,
                    {
                        "state": state,
                        "lease_uid": None,
                        "lease_until": None,
                        "error": "",
                        "finished_at": finished,
                    },
                ),
                *plan,
                self.audit("runs", uid, action, expected + 1, ["state", "lease_until", "error"]),
            ]
        )
        return self.get("runs", uid)

    def result_rows(self, uid):
        row = self.raw("runs", uid)
        if row["state"] != "succeeded":
            raise ReportingError(409, "incomplete", "A successful run is required for results")
        self.sources.authorize(KINDS[row["config"]["kind"]], self.store.data_source_uid)
        steps = self.steps(uid)
        return row, steps, [r for s in steps for r in s["records"]]

    def result(self, uid):
        row, steps, _ = self.result_rows(uid)
        return {
            "summary": row["summary"],
            "kind": row["config"]["kind"],
            "search": row["config"]["search"],
            "sources": [
                {
                    "source": s["source"],
                    "captured_at": s["captured_at"],
                    "record_count": len(s["records"]),
                }
                for s in steps
            ],
            "capture_started_at": row["created_at"],
            "capture_finished_at": row["finished_at"],
            "notice": "Source steps were captured at different times. These saved results are not a point-in-time accounting statement.",
        }

    def rows(self, uid, *, page_index=0, page_size=25, search=""):
        _, _, rows = self.result_rows(uid)
        if search:
            rows = [r for r in rows if search.casefold() in r["name"].casefold()]
        return page(
            rows[page_index * page_size : (page_index + 1) * page_size],
            len(rows),
            page_index,
            page_size,
        )

    def verify(self, uid):
        _, _, rows = self.result_rows(uid)
        ports = {}
        changes = []
        unchanged = 0
        for row in rows:
            if row["source"] not in ports:
                ports[row["source"]] = self.sources.port(row["source"], self.store.data_source_uid)
            try:
                current = ports[row["source"]].get(row["source_uid"])
                status = "unchanged" if current["version"] == row["version"] else "changed"
            except ReportingError as e:
                if e.status != 404:
                    raise
                status = "missing"
            if status == "unchanged":
                unchanged += 1
            else:
                changes.append(
                    {
                        "source": row["source"],
                        "source_uid": row["source_uid"],
                        "name": row["name"],
                        "path": row["path"],
                        "status": status,
                    }
                )
        return {
            "checked": len(rows),
            "unchanged": unchanged,
            "changes": changes,
            "checked_at": now().isoformat(),
            "notice": "Checks compare captured record versions with current source records; new source records require a fresh run.",
        }

    def export(self, uid):
        _, _, rows = self.result_rows(uid)
        columns = [
            "source",
            "source_uid",
            "name",
            "state",
            "version",
            "company_name",
            "currency_code",
            "net_total",
            "total",
            "allocated",
            "remaining",
            "path",
        ]
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([csv_safe(row.get(k, "")) for k in columns])
        return {
            "filename": f"report-{uid}.csv",
            "content": output.getvalue(),
            "mime": "text/csv;charset=utf-8",
        }

    def schedule_state(self, uid, action, expected):
        self.require("reporting.manage")
        row = self.raw("schedules", uid)
        plan = []
        before, after = ("paused", "active") if action == "activate" else ("active", "paused")
        if row["state"] != before:
            raise ReportingError(409, "state", "Schedule is not in the required state")
        values = {"state": after, "last_error": ""}
        if action == "activate":
            definition = self.raw("definitions", row["definition_uid"])
            if definition["state"] != "active":
                raise ReportingError(409, "archived", "Restore the saved report before activation")
            plan.append(self.guard(Definition, definition, definition["version"], bump=False))
            values["next_run_at"] = now()
        self.transact(
            [
                self.guard(Schedule, row, expected, values),
                *plan,
                self.audit("schedules", uid, action, expected + 1, values),
            ]
        )
        return self.get("schedules", uid)

    def due(self):
        self.require("reporting.manage")
        self.require("reporting.run")
        rows = self.store.read(
            select(Schedule.__table__)
            .where(
                Schedule.created_by_uid == self.actor_uid,
                Schedule.state == "active",
                Schedule.next_run_at <= now(),
            )
            .order_by(Schedule.next_run_at, Schedule.uid)
            .limit(20)
        )
        for row in rows:
            if self.store.read(
                select(Run.uid)
                .where(Run.schedule_uid == key(row["uid"]), Run.state.in_(["queued", "running"]))
                .limit(1)
            ):
                continue
            definition = self.raw("definitions", row["definition_uid"])
            if definition["state"] != "active":
                self.transact(
                    [
                        self.guard(
                            Schedule,
                            row,
                            row["version"],
                            {
                                "state": "paused",
                                "last_error": "Saved report is archived; restore it before reactivating.",
                            },
                        ),
                        self.audit(
                            "schedules",
                            row["uid"],
                            "pause-archived",
                            row["version"] + 1,
                            ["state", "last_error"],
                        ),
                    ]
                )
                return None
            due = timestamp(row["next_run_at"])
            uid = uuid5(key(row["uid"]), due.isoformat())
            self.transact(
                [
                    self.guard(
                        Schedule,
                        row,
                        row["version"],
                        {
                            "next_run_at": now() + timedelta(minutes=row["interval_minutes"]),
                            "last_run_uid": uid,
                            "last_error": "",
                        },
                    ),
                    *self.run_plan(definition, uid, schedule=row, due=due),
                    self.audit(
                        "schedules",
                        row["uid"],
                        "queue-due",
                        row["version"] + 1,
                        ["next_run_at", "last_run_uid"],
                    ),
                ]
            )
            return str(uid)
        return None

    def tick(self):
        self.require("reporting.manage")
        self.require("reporting.run")
        scheduled = self.due()
        rows = self.store.read(
            select(Run.__table__)
            .where(
                Run.created_by_uid == self.actor_uid,
                Run.state.in_(["queued", "running"]),
                Run.lease_uid.is_(None),
            )
            .order_by(Run.created_at, Run.uid)
            .limit(1)
        )
        result = self.advance(rows[0]["uid"], rows[0]["version"]) if rows else None
        return {
            "scheduled_uid": scheduled,
            "run_uid": result["uid"] if result else None,
            "state": result["state"] if result else "idle",
        }

    def history(self, resource, uid):
        self.raw(resource, uid)
        return {
            "items": self.store.read(
                select(AuditEvent.__table__)
                .where(
                    AuditEvent.resource == resource,
                    AuditEvent.record_uid == key(uid),
                    AuditEvent.actor_uid == self.actor_uid,
                )
                .order_by(AuditEvent.occurred_at.desc())
                .limit(100)
            )
        }


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


def csv_safe(value):
    text = str(value)
    return (
        "'" + text
        if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n"))
        or text.startswith(("\t", "\r", "\n"))
        else text
    )
