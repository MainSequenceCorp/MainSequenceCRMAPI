import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import insert, select

from api.erp.projects.local import create_app
from metatables import MetaTable, upgrade_application
from src.erp.projects.dependencies import Dependencies
from src.erp.projects.errors import ProjectsError
from src.erp.projects.metatables import AuditEvent, Project
from src.erp.projects.service import Service


def effort(task, **changes):
    return {
        "request_uid": uuid4(),
        "expected_task_version": task["version"],
        "expected_project_version": task["project_version"],
        "work_date": date.today(),
        "minutes": 45,
        "description": "Delivered fixture work",
        **changes,
    }


def test_independent_delivery_effort_and_history(business):
    svc = business["service"]
    project = business["new"]()
    task = business["task"](project)
    project = svc.get("projects", project["uid"])
    project = svc.transition(project["uid"], "start", project["version"])
    task = svc.get("tasks", task["uid"])
    result = svc.log_time(task["uid"], effort(task))
    task = result["task"]
    entry = result["entry"]
    assert (
        task["recorded_minutes"] == 45
        and svc.get("projects", project["uid"])["recorded_minutes"] == 45
    )
    with pytest.raises(ProjectsError) as open_tasks:
        svc.transition(project["uid"], "deliver", task["project_version"])
    assert open_tasks.value.code == "open_tasks"
    result = svc.void_time(
        entry["uid"],
        {
            "expected_version": entry["version"],
            "expected_task_version": task["version"],
            "expected_project_version": task["project_version"],
            "reason": "Duplicate entry",
        },
    )
    task = result["task"]
    assert (
        task["recorded_minutes"] == 0 and svc.history(task["uid"])["items"][0]["state"] == "voided"
    )
    task = svc.task_state(task["uid"], "done", task["version"], task["project_version"])
    project = svc.transition(project["uid"], "deliver", task["project_version"])
    with pytest.raises(ProjectsError):
        svc.log_time(task["uid"], effort(task))
    project = svc.transition(project["uid"], "reopen", project["version"])
    task = svc.get("tasks", task["uid"])
    task = svc.task_state(task["uid"], "todo", task["version"], task["project_version"])
    task = svc.task_state(task["uid"], "in_progress", task["version"], task["project_version"])
    task = svc.task_state(task["uid"], "done", task["version"], task["project_version"])
    project = svc.transition(project["uid"], "deliver", task["project_version"])
    project = svc.transition(project["uid"], "close", project["version"])
    assert project["state"] == "closed"
    with pytest.raises(ProjectsError):
        svc.transition(project["uid"], "reopen", project["version"])


def test_task_creation_races_delivery_with_parent_fence(business):
    svc = business["service"]
    project = business["new"]()
    task = business["task"](project)
    project = svc.transition(project["uid"], "start", task["project_version"])
    task = svc.get("tasks", task["uid"])
    task = svc.task_state(task["uid"], "done", task["version"], task["project_version"])
    project = svc.get("projects", project["uid"])

    def change(which):
        try:
            return (
                svc.transition(project["uid"], "deliver", project["version"])
                if which
                else business["task"](project, name="Concurrent new work")
            )
        except ProjectsError as error:
            return error

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(change, [0, 1]))
    assert sum(isinstance(row, dict) for row in results) == 1
    assert next(row for row in results if isinstance(row, ProjectsError)).status == 409
    saved = svc.get("projects", project["uid"])
    assert not (saved["state"] == "delivered" and saved["task_counts"].get("todo"))


def test_permissions_dates_assignments_and_rollback(business):
    svc = business["service"]
    project = business["new"]()
    with pytest.raises(ValidationError):
        business["new"](start_date=date.today(), due_date=date.today() - timedelta(days=1))
    with pytest.raises(ProjectsError):
        business["task"](project, assignee_party_uid=business["party"]["uid"])
    with pytest.raises(ProjectsError):
        svc.transition(project["uid"], "deliver", project["version"])
    reader = Service(svc.store, svc.actor_uid, {"projects.read"}, svc.dependencies)
    with pytest.raises(ProjectsError) as denied:
        reader.save_project(business["payload"])
    assert denied.value.status == 403
    with pytest.raises(ProjectsError):
        svc.transact(
            [
                svc.guard("projects", project, 1, {"description": "Must roll back"}),
                svc.audit("projects", project["uid"], "bad-test", 99, ["description"]),
                insert(Project).values(uid=uuid4()),
            ]
        )
    assert svc.get("projects", project["uid"])["version"] == 1
    assert not svc.store.read(
        select(AuditEvent.__table__).where(
            AuditEvent.record_uid == UUID(project["uid"]), AuditEvent.version == 99
        )
    )
    task = business["task"](project)
    project = svc.transition(project["uid"], "start", task["project_version"])
    task = svc.get("tasks", task["uid"])
    for amount in [0, 1441, 1.5, True]:
        with pytest.raises(ValidationError):
            svc.log_time(task["uid"], effort(task, minutes=amount))
    with pytest.raises(ProjectsError):
        svc.log_time(task["uid"], effort(task, work_date=date.today() + timedelta(days=1)))
    result = svc.log_time(task["uid"], effort(task))
    task = result["task"]
    entry = result["entry"]
    outsider = Service(svc.store, uuid4(), {"projects.read", "projects.write"}, svc.dependencies)
    with pytest.raises(ProjectsError):
        outsider.void_time(
            entry["uid"],
            {
                "expected_version": 1,
                "expected_task_version": task["version"],
                "expected_project_version": task["project_version"],
                "reason": "Denied",
            },
        )


def test_service_order_delivery_billing_atomic_trace(business):
    from tests.erp.finance.conftest import business as finance_business
    from tests.erp.finance.conftest import finance_services
    from tests.erp.sales.conftest import business as sales_business
    from tests.erp.sales.conftest import services as sales_services

    from src.erp.finance.dependencies import Dependencies as FinanceDependencies
    from src.erp.finance.sales_integration import SalesPort as FinanceSales
    from src.erp.projects.integrations import FinancePort, SalesPort

    sales_gen = sales_business.__wrapped__(sales_services.__wrapped__())
    sales = next(sales_gen)
    finance_gen = finance_business.__wrapped__(finance_services.__wrapped__())
    finance = next(finance_gen)
    svc = business["service"]
    original = svc.dependencies
    fsvc = finance["service"]
    foriginal = fsvc.dependencies
    svc.dependencies = Dependencies(
        business["base"],
        lambda: SalesPort(sales["sales"], sales["catalog"]),
        lambda: FinancePort(fsvc),
    )
    fsvc.dependencies = FinanceDependencies(finance["base"], lambda: FinanceSales(sales["sales"]))
    try:
        order = sales["new"]()
        order = sales["sales"].transition(order["uid"], "confirm", 1)
        uid = uuid4()
        business["projects"].append(uid)
        args = {
            "request_uid": uid,
            "order_uid": order["uid"],
            "expected_order_version": order["version"],
            "name": "Service " + uuid4().hex[:12],
        }
        project = svc.from_sales(args)
        task = svc.collection("tasks", project_uid=uid)["items"][0]
        linked = sales["sales"].get(order["uid"])
        assert f"projects:{uid}" in linked["downstream"]
        duplicate = uuid4()
        business["projects"].append(duplicate)
        with pytest.raises(ProjectsError):
            svc.from_sales(
                {
                    **args,
                    "request_uid": duplicate,
                    "name": "Duplicate " + uuid4().hex[:8],
                    "expected_order_version": linked["version"],
                }
            )
        assert sales["sales"].get(order["uid"])["version"] == linked["version"]
        project = svc.transition(uid, "start", project["version"])
        task = svc.get("tasks", task["uid"])
        task = svc.task_state(task["uid"], "done", task["version"], task["project_version"])
        project = svc.transition(uid, "deliver", task["project_version"])
        invoice_uid = uuid4()
        finance["documents"].append(("invoices", invoice_uid))
        bill = {
            "request_uid": invoice_uid,
            "expected_version": project["version"],
            "name": "BILL-" + uuid4().hex[:12].upper(),
            "document_date": date.today(),
            "due_date": date.today(),
            "tax_rate": "20",
        }
        with pytest.raises(ProjectsError):
            svc.bill(uid, {**bill, "expected_version": 1})
        with pytest.raises(Exception) as absent:
            fsvc.get("invoices", invoice_uid)
        assert absent.value.status == 404
        project = svc.bill(uid, bill)
        invoice = fsvc.get("invoices", invoice_uid)
        assert project["state"] == "closed" and project["invoice_uid"] == str(invoice_uid)
        assert (
            invoice["source_order_uid"] == order["uid"]
            and invoice["net_total"] == order["net_total"]
        )
        assert f"finance:{invoice_uid}" in sales["sales"].get(order["uid"])["downstream"]
        with pytest.raises(ProjectsError):
            svc.bill(uid, {**bill, "expected_version": project["version"]})
        assert invoice["state"] == "draft"
    finally:
        svc.dependencies = original
        fsvc.dependencies = foriginal
        for generator in [finance_gen, sales_gen]:
            try:
                next(generator)
            except StopIteration:
                pass


def test_migrations_http_contract_and_independent_restart(business):
    row = business["new"]()
    ids = [
        "erp_base.alembic_version",
        "erp_catalog.alembic_version",
        "erp_sales.alembic_version",
        "erp_finance.alembic_version",
        "mainsequence_crm.alembic_version",
    ]
    before = {r.identifier: r.alembic_revision for r in MetaTable.filter(identifier__in=ids)}
    assert upgrade_application("src.erp.projects.migrations:migration")["revision"] == "0001"
    assert before == {
        r.identifier: r.alembic_revision for r in MetaTable.filter(identifier__in=ids)
    }
    code = """from metatables import configure_local_client
configure_local_client()
from api.erp.projects.main import create_app
from src.erp.projects.store import Store
from src.erp.projects.metatables import Project
from sqlalchemy import select
from uuid import UUID
import sys
assert not any(k.startswith(('src.erp.crm','src.erp.sales','src.erp.finance','src.erp.catalog')) for k in sys.modules)
assert not any(r.path.startswith('/api/projects') for r in create_app(enabled=False).routes)
print(Store(local_only=True).read(select(Project.__table__).where(Project.uid==UUID(sys.argv[1])))[0]['uid'])
"""
    assert (
        subprocess.run(
            [sys.executable, "-c", code, row["uid"]], capture_output=True, text=True, check=True
        ).stdout.strip()
        == row["uid"]
    )
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    root = Path("tests/erp/projects/contracts/sdk-0.5.19/schemas")
    schemas = [json.loads(p.read_text()) for p in root.glob("*.json")]
    registry = Registry().with_resources([(s["$id"], Resource.from_contents(s)) for s in schemas])
    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 51000)
    ) as client:
        assert client.get("/api/projects/v1/ready/").json()["local"] is True
        for resource in ["projects", "tasks"]:
            for suffix, name in [
                ("", "resource-collection-v1"),
                ("discovery/", "resource-discovery-v1"),
            ]:
                response = client.get(f"/api/projects/v1/{resource}/{suffix}")
                assert response.status_code == 200, response.text
                Draft202012Validator(
                    json.loads((root / (name + ".schema.json")).read_text()), registry=registry
                ).validate(response.json())
        assert (
            client.get("/api/projects/v1/ready/", headers={"x-user-uid": str(uuid4())}).status_code
            == 401
        )
        assert (
            client.get(
                "/api/projects/v1/ready/", headers={"Origin": "https://outside.example"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/projects/v1/projects/{row['uid']}/actions/start/",
                json={"expected_version": 0},
            ).status_code
            == 422
        )


def test_billing_validation_and_people_lookup(business):
    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 51000)
    ) as client:
        response = client.get(
            "/api/projects/v1/references/people/", params={"search": business["person"]["name"]}
        )
        assert response.status_code == 200, response.text
        assert response.json()["items"][0]["uid"] == business["person"]["uid"]
        assert all(row["kind"] == "person" for row in response.json()["items"])
        data = {
            "request_uid": str(uuid4()),
            "expected_version": 1,
            "name": "BAD-TERMS",
            "document_date": str(date.today()),
            "due_date": str(date.today()),
            "tax_rate": "20",
        }
        for changes in [
            {"tax_rate": "NaN"},
            {"tax_rate": "101"},
            {"due_date": str(date.today() - timedelta(days=1))},
        ]:
            assert (
                client.post(
                    f"/api/projects/v1/projects/{uuid4()}/bill/", json={**data, **changes}
                ).status_code
                == 422
            )
