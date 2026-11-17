"""Owned disposable reporting fixtures on actual verified SQLite, with owner cleanup."""

import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from tests.erp.commerce.conftest import business, commerce, services  # noqa: F401

from metatables import upgrade_application
from src.erp.reporting.metatables import AuditEvent, Definition, Run, RunStep, Schedule
from src.erp.reporting.service import Service
from src.erp.reporting.sources import ReadPort, Sources
from src.erp.reporting.store import Store, require_local_runtime


@pytest.fixture
def reporting(commerce):  # noqa: F811
    f = commerce
    assert os.environ.get("REPORTING_LOCAL_SOURCE_UID") == str(require_local_runtime())
    upgrade_application("src.erp.reporting.migrations:migration")
    s = Service(
        Store(local_only=True),
        f["sales"].actor_uid,
        {"reporting.read", "reporting.write", "reporting.run", "reporting.manage"},
        Sources(
            {
                "sales": lambda: ReadPort("sales", f["sales"]),
                "finance": lambda: ReadPort("finance", f["finance"]),
            }
        ),
    )
    owned = {"definitions": [], "runs": [], "schedules": []}

    def definition(**changes):
        uid = uuid4()
        owned["definitions"].append(uid)
        return s.save(
            "definitions",
            {
                "name": "Report " + uid.hex[:8],
                "kind": "commercial",
                "search": f["base"].get("parties", f["payload"]["customer_uid"])["name"],
                **changes,
            },
            request_uid=uid,
        )

    def queue(d=None):
        d = d or definition()
        uid = uuid4()
        owned["runs"].append(uid)
        return s.queue(
            {
                "request_uid": uid,
                "definition_uid": d["uid"],
                "expected_definition_version": d["version"],
            }
        )

    def finish(row):
        for _ in range(4):
            if row["state"] in {"succeeded", "failed", "cancelled"}:
                break
            row = s.advance(row["uid"], row["version"])
        return row

    def schedule(d=None, **changes):
        d = d or definition()
        uid = uuid4()
        owned["schedules"].append(uid)
        return s.save(
            "schedules",
            {
                "name": "Schedule " + uid.hex[:8],
                "definition_uid": d["uid"],
                "interval_minutes": 60,
                **changes,
            },
            request_uid=uid,
        )

    try:
        yield {
            **f,
            "reporting": s,
            "definition": definition,
            "queue_report": queue,
            "finish_report": finish,
            "schedule_report": schedule,
            "reporting_owned": owned,
        }
    finally:
        # Browser-created definitions and child runs/schedules are scoped to tracked IDs.
        for model, kind in [(Run, "runs"), (Schedule, "schedules")]:
            if owned["definitions"]:
                for r in s.store.read(
                    select(model.uid)
                    .where(model.definition_uid.in_(owned["definitions"]))
                    .limit(100)
                ):
                    if UUID(r["uid"]) not in owned[kind]:
                        owned[kind].append(UUID(r["uid"]))
        for resource, model in [
            ("runs", Run),
            ("schedules", Schedule),
            ("definitions", Definition),
        ]:
            for uid in set(owned[resource]):
                statements = [
                    delete(AuditEvent).where(
                        AuditEvent.resource == resource, AuditEvent.record_uid == uid
                    )
                ]
                if resource == "runs":
                    statements.insert(0, delete(RunStep).where(RunStep.run_uid == uid))
                s.store.write([*statements, delete(model).where(model.uid == uid)])
