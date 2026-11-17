from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, insert, select, update
from tests.erp.inventory.conftest import inventory_services, stock  # noqa: F401
from tests.erp.manufacturing.conftest import manufacturing  # noqa: F401
from tests.erp.purchasing.conftest import purchase  # noqa: F401

from src.erp.reporting.errors import ReportingError
from src.erp.reporting.metatables import Run, RunStep, Schedule
from src.erp.reporting.schemas import DefinitionInput, ScheduleInput, VersionInput
from src.erp.reporting.service import Service, csv_safe, now
from src.erp.reporting.sources import ReadPort, Sources, summarize


def error(status, fn):
    with pytest.raises(ReportingError) as e:
        fn()
    assert e.value.status == status, e.value.message


def commercial(f):
    row, _ = f["checkout"](f["access"]["token"], f["site"], f["offer"])
    private = f["commerce"].get("checkouts", row["uid"])
    private = f["invoice"](private, tax_rate="20")
    private["allocation"] = f["pay"](private)
    return private


def test_commercial_snapshot_totals_source_recheck_and_export(reporting):
    f = reporting
    s = f["reporting"]
    checkout = commercial(f)
    d = f["definition"]()
    row = f["finish_report"](f["queue_report"](d))
    assert row["state"] == "succeeded" and row["progress"] == 2
    result = s.result(row["uid"])
    totals = result["summary"]["totals"]
    assert len(totals) == 1
    assert {
        k: Decimal(totals[0][k])
        for k in ["order_net", "invoice_net", "invoice_total", "allocated", "remaining"]
    } == {"order_net": 25, "invoice_net": 25, "invoice_total": 30, "allocated": 30, "remaining": 0}
    assert result["summary"]["links"][0]["status"] == "matched"
    assert s.rows(row["uid"], page_size=1)["pageInfo"]["hasNextPage"]
    assert s.verify(row["uid"])["unchanged"] == 2
    assert "25.00" in s.export(row["uid"])["content"]
    allocation = checkout["allocation"]
    f["finance"].reverse_allocation(
        allocation["allocation_uid"],
        allocation["invoice"]["version"],
        allocation["payment"]["version"],
    )
    assert s.verify(row["uid"])["changes"][0]["status"] == "changed"
    assert s.result(row["uid"]) == result
    assert csv_safe("  =2+2").startswith("'") and csv_safe("\tformula").startswith("'")
    # Deliberate different-currency numeric cases cannot be combined into one total.
    rows = s.rows(row["uid"])["items"]
    other = {
        **rows[0],
        "currency_uid": str(uuid4()),
        "currency_code": "USD",
        "net_total": "9007199254740993.01",
    }
    sums = summarize("commercial", [*rows, other])["totals"]
    assert len(sums) == 2
    assert any(Decimal(x["order_net"]) == Decimal("9007199254740993.01") for x in sums)


def test_creator_scope_permissions_immutable_configuration_and_disabled_sources(
    reporting, monkeypatch
):
    f = reporting
    s = f["reporting"]
    d = f["definition"]()
    run = f["queue_report"](d)
    other = Service(s.store, uuid4(), s.capabilities, s.sources)
    assert other.collection("definitions")["items"] == []
    for resource, uid in [("definitions", d["uid"]), ("runs", run["uid"])]:
        error(404, lambda: other.get(resource, uid))
    denied = Service(s.store, s.actor_uid, {"reporting.read"}, s.sources)
    error(403, lambda: denied.advance(run["uid"], run["version"]))
    s.save(
        "definitions",
        {"name": d["name"], "kind": "operations", "search": "different"},
        uid=d["uid"],
        expected_version=d["version"],
    )
    assert s.get("runs", run["uid"])["config"]["kind"] == "commercial"
    with monkeypatch.context() as p:
        p.delitem(s.sources.factories, "sales")
        failed = s.advance(run["uid"], run["version"])
        assert failed["state"] == "failed" and "source_disabled" in failed["error"]
    retry = s.control(run["uid"], "retry", failed["version"])
    success = f["finish_report"](retry)
    assert success["state"] == "succeeded"
    with monkeypatch.context() as p:
        p.setattr(f["sales"], "capabilities", set())
        error(403, lambda: s.result(run["uid"]))
        error(403, lambda: s.export(run["uid"]))
    with monkeypatch.context() as p:
        p.setattr(f["sales"].store, "data_source_uid", str(uuid4()))
        error(503, lambda: s.result(run["uid"]))
    error(409, lambda: s.control(run["uid"], "retry", success["version"]))
    for cls, payload in [
        (DefinitionInput, {"name": "SQL", "kind": "python", "code": "eval(x)"}),
        (VersionInput, {"expected_version": True}),
        (ScheduleInput, {"name": "Bad", "definition_uid": d["uid"], "interval_minutes": True}),
    ]:
        with pytest.raises(ValidationError):
            cls.model_validate(payload)


def test_concurrent_claim_cancellation_expiry_and_recovery(reporting):
    f = reporting
    s = f["reporting"]
    run = f["queue_report"]()
    barrier = Barrier(2)

    def claim(_):
        barrier.wait()
        try:
            return s.claim(run["uid"], run["version"])
        except ReportingError as e:
            return e.status

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(claim, range(2)))
    won = next(x for x in results if isinstance(x, tuple))
    assert results.count(409) == 1
    row, step = won
    error(409, lambda: s.control(row["uid"], "recover", row["version"]))
    cancelled = s.control(row["uid"], "cancel", row["version"])
    assert cancelled["state"] == "cancelled"
    error(409, lambda: s.finish(row, step, []))
    assert s.get("runs", row["uid"])["progress"] == 0
    run = f["queue_report"]()
    row, step = s.claim(run["uid"], run["version"])
    s.store.write(
        [
            update(Run)
            .where(Run.uid == UUID(row["uid"]))
            .values(lease_until=now() - timedelta(seconds=1))
        ]
    )
    error(409, lambda: s.finish(row, step, []))
    recovered = s.control(row["uid"], "recover", row["version"])
    assert recovered["state"] == "queued"
    assert f["finish_report"](recovered)["state"] == "succeeded"
    assert s.get("runs", row["uid"])["steps"][0]["attempts"] == 2


def test_failed_step_preserves_progress_bounds_and_no_secret_errors(reporting, monkeypatch):
    f = reporting
    s = f["reporting"]
    run = f["queue_report"]()
    run = s.advance(run["uid"], run["version"])
    assert run["progress"] == 1
    original = f["finance"].collection
    with monkeypatch.context() as p:
        p.setattr(
            f["finance"],
            "collection",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("secret-token-must-not-escape")),
        )
        run = s.advance(run["uid"], run["version"])
        assert run["state"] == "failed" and run["progress"] == 1
        assert "secret-token" not in str(run) and "secret-token" not in str(
            s.history("runs", run["uid"])
        )
    run = s.control(run["uid"], "retry", run["version"])
    assert f["finish_report"](run)["state"] == "succeeded"
    assert s.get("runs", run["uid"])["steps"][0]["attempts"] == 1
    run = f["queue_report"]()
    run = s.advance(run["uid"], run["version"])
    with monkeypatch.context() as p:
        p.setattr(
            f["finance"],
            "collection",
            lambda *a, **kw: {"items": [], "pageInfo": {"totalItems": 201}},
        )
        run = s.advance(run["uid"], run["version"])
        assert run["state"] == "failed" and "source_limit" in run["error"]
    assert original is not None
    error(409, lambda: s.result(run["uid"]))


def test_schedule_claim_no_overlap_pause_archive_and_late_rollback(reporting, monkeypatch):
    f = reporting
    s = f["reporting"]
    d = f["definition"]()
    schedule = f["schedule_report"](d)
    schedule = s.schedule_state(schedule["uid"], "activate", schedule["version"])
    barrier = Barrier(2)

    def due(_):
        barrier.wait()
        try:
            return s.due()
        except ReportingError as e:
            return e.status

    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(due, range(2)))
    run_uid = next(x for x in outcomes if isinstance(x, str))
    run = s.get("runs", run_uid)
    assert len(s.store.read(select(Run.uid).where(Run.schedule_uid == UUID(schedule["uid"])))) == 1
    s.store.write(
        [
            update(Schedule)
            .where(Schedule.uid == UUID(schedule["uid"]))
            .values(next_run_at=now() - timedelta(minutes=1))
        ]
    )
    assert s.due() is None
    assert f["finish_report"](run)["state"] == "succeeded"
    before = s.get("schedules", schedule["uid"])
    original = s.run_plan

    def invalid(*args, **kwargs):
        return [*original(*args, **kwargs), insert(RunStep).values(uid=uuid4())]

    with monkeypatch.context() as p:
        p.setattr(s, "run_plan", invalid)
        error(409, s.due)
    assert s.get("schedules", schedule["uid"])["version"] == before["version"]
    assert len(s.store.read(select(Run.uid).where(Run.schedule_uid == UUID(schedule["uid"])))) == 1
    paused = s.schedule_state(schedule["uid"], "pause", before["version"])
    assert s.due() is None
    active = s.schedule_state(schedule["uid"], "activate", paused["version"])
    s.definition_state(d["uid"], "archive", d["version"])
    assert s.due() is None
    paused = s.get("schedules", active["uid"])
    assert paused["state"] == "paused" and "archived" in paused["last_error"]


def test_operations_sources_use_public_owner_reads(reporting, manufacturing, purchase):  # noqa: F811
    from src.erp.projects.dependencies import Dependencies
    from src.erp.projects.metatables import AuditEvent, Project
    from src.erp.projects.service import Service as ProjectsService
    from src.erp.projects.store import Store as ProjectsStore

    f = reporting
    s = f["reporting"]
    m = manufacturing
    p = purchase
    prefix = "OPS-" + uuid4().hex[:8].upper()
    production = m["batch"](name=prefix + "-M")
    movement = m["movement"](name=prefix + "-I")
    order = p["new_purchase"](name=prefix + "-P")
    projects = ProjectsService(
        ProjectsStore(local_only=True),
        s.actor_uid,
        {"projects.read", "projects.write", "projects.manage", "projects.configure"},
        Dependencies(m["base"]),
    )
    uid = uuid4()
    try:
        project = projects.save_project(
            {
                "name": "=" + prefix + "-J",
                "description": "Disposable reporting fixture",
                "customer_uid": m["payload"]["customer_uid"],
                "operating_company_uid": m["payload"]["operating_company_uid"],
            },
            request_uid=uid,
        )
        sources = {
            "projects": projects,
            "inventory": m["service"],
            "purchasing": p["purchasing"],
            "manufacturing": m["manufacturing"],
        }
        s.sources = Sources(
            {name: lambda name=name: ReadPort(name, sources[name]) for name in sources}
        )
        run = f["finish_report"](
            f["queue_report"](f["definition"](kind="operations", search=prefix))
        )
        assert run["state"] == "succeeded"
        rows = s.rows(run["uid"])["items"]
        assert {r["source_uid"] for r in rows} == {
            production["uid"],
            movement["uid"],
            order["uid"],
            project["uid"],
        }
        assert (
            s.result(run["uid"])["summary"]["record_count"] == 4
            and s.verify(run["uid"])["unchanged"] == 4
        )
        assert "'=" + prefix in s.export(run["uid"])["content"]
    finally:
        projects.store.write(
            [
                delete(AuditEvent).where(AuditEvent.record_uid == uid),
                delete(Project).where(Project.uid == uid),
            ]
        )


def test_http_contracts_fresh_process_and_independent_migration(reporting):
    import json
    import subprocess
    from pathlib import Path

    from fastapi.testclient import TestClient
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    from api.erp.reporting.local import create_app
    from metatables import upgrade_application
    from src.erp.reporting.metatables import MODELS

    f = reporting
    d = f["definition"]()
    assert upgrade_application("src.erp.reporting.migrations:migration")["revision"] == "0001"
    assert {m.__metatable_namespace__ for m in MODELS} == {"erp-reporting"}
    code = """import sys
from metatables import configure_local_client
configure_local_client()
from api.erp.reporting.main import create_app
from src.erp.reporting.store import Store
from src.erp.reporting.metatables import Definition
from sqlalchemy import select
from uuid import UUID
assert not any(k.startswith(('src.erp.sales','src.erp.finance','src.erp.inventory','src.erp.crm')) for k in sys.modules)
assert not any(r.path.startswith('/api/reporting') for r in create_app(enabled=False).routes)
print(Store(local_only=True).read(select(Definition.uid).where(Definition.uid==UUID(sys.argv[1])))[0]['uid'])
"""
    assert d["uid"] in subprocess.check_output(
        [".venv/bin/python", "-c", code, d["uid"]], text=True
    )
    schemas = [
        json.loads(p.read_text())
        for p in Path("tests/erp/reporting/contracts/sdk-0.5.19/schemas").glob("*.json")
    ]
    registry = Registry().with_resources([(x["$id"], Resource.from_contents(x)) for x in schemas])
    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 50000)
    ) as client:
        response = client.get("/api/reporting/v1/ready/")
        assert response.status_code == 200, response.text
        assert response.json()["schema_revision"] == "0001"
        for resource in ["definitions", "runs", "schedules"]:
            for suffix, name in [("", "resource-collection"), ("discovery/", "resource-discovery")]:
                response = client.get(f"/api/reporting/v1/{resource}/{suffix}")
                assert response.status_code == 200, response.text
                Draft202012Validator(
                    next(x for x in schemas if name in x["$id"]), registry=registry
                ).validate(response.json())
        for headers in [
            {"x-user-uid": str(uuid4())},
            {"Origin": "https://external.example"},
            {"Host": "external.example"},
        ]:
            assert client.get("/api/reporting/v1/ready/", headers=headers).status_code in (401, 403)
        assert client.get("/api/reporting/v1/runs/?code=eval").status_code == 422
        assert (
            client.post(
                f"/api/reporting/v1/definitions/{d['uid']}/archive/",
                json={"expected_version": True},
            ).status_code
            == 422
        )
        run = f["queue_report"](d)
        for _ in range(2):
            response = client.post(
                f"/api/reporting/v1/runs/{run['uid']}/advance/",
                json={"expected_version": run["version"]},
            )
            assert response.status_code == 200, response.text
            run = response.json()
        assert run["state"] == "succeeded", run
        for suffix, name in [
            ("rows/", "resource-collection"),
            ("rows/discovery/", "resource-discovery"),
        ]:
            response = client.get(f"/api/reporting/v1/runs/{run['uid']}/{suffix}")
            assert response.status_code == 200, response.text
            Draft202012Validator(
                next(x for x in schemas if name in x["$id"]), registry=registry
            ).validate(response.json())
        assert (
            client.get(f"/api/reporting/v1/runs/{run['uid']}/result/").headers["cache-control"]
            == "no-store"
        )
        assert client.post("/api/reporting/v1/worker/tick/", json={}).status_code == 200
        assert client.get("/api/reporting/v1/worker/status/").json()["available"]
