import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from referencing import Registry, Resource
from sqlalchemy import insert, select

from api.erp.people.local import create_app
from metatables import MetaTable, upgrade_application
from src.erp.people.errors import PeopleError
from src.erp.people.metatables import AuditEvent, Employee
from src.erp.people.service import Service


def act(svc, row, action, **changes):
    return svc.absence_action(
        row["uid"],
        action,
        {
            "expected_version": row["version"],
            "expected_employee_version": svc.get("employees", row["employee_uid"])["version"],
            "note": "Reviewed request",
            **changes,
        },
    )


def employee_data(row, **changes):
    return {
        k: changes.get(k, row[k])
        for k in (
            "person_uid",
            "operating_company_uid",
            "department_uid",
            "job_title",
            "start_date",
            "end_date",
        )
    }


def test_workforce_identity_departments_and_archive(workforce):
    f = workforce
    svc = f["service"]
    department = f["department"]()
    emp = f["employee"](department_uid=department["uid"])
    assert emp["person_uid"] == f["person"]["uid"] and emp["uid"] != emp["person_uid"]
    assert (
        "user_uid" not in emp and svc.get("departments", department["uid"])["active_members"] == 1
    )
    with pytest.raises(PeopleError) as duplicate:
        f["employee"]()
    assert duplicate.value.status == 409
    with pytest.raises(PeopleError) as members:
        svc.archive("departments", department["uid"], "archive", 2)
    assert members.value.code == "active_members"
    emp = svc.save_employee(
        employee_data(emp, job_title="Lead consultant"), uid=emp["uid"], expected_version=1
    )
    with pytest.raises(PeopleError) as stale:
        svc.save_employee(employee_data(emp, job_title="Stale"), uid=emp["uid"], expected_version=1)
    assert stale.value.status == 409
    emp = svc.archive("employees", emp["uid"], "archive", emp["version"])
    department = svc.get("departments", department["uid"])
    department = svc.archive("departments", department["uid"], "archive", department["version"])
    with pytest.raises(PeopleError):
        svc.archive("employees", emp["uid"], "restore", emp["version"])
    svc.archive("departments", department["uid"], "restore", department["version"])
    assert svc.archive("employees", emp["uid"], "restore", emp["version"])["state"] == "active"


def test_absence_decision_history_overlap_and_separation(workforce):
    f = workforce
    svc = f["service"]
    emp = f["employee"]()
    row = f["absence"](emp)
    assert row["calendar_days"] == 3
    row = act(svc, row, "submit")
    with pytest.raises(PeopleError) as self_approval:
        act(svc, row, "approve")
    assert self_approval.value.code == "self_approval"
    approver = Service(svc.store, uuid4(), svc.capabilities, svc.dependencies)
    row = act(approver, row, "approve")
    decided = row["decision_by_uid"]
    assert decided == str(approver.actor_uid)
    emp = svc.get("employees", emp["uid"])
    with pytest.raises(PeopleError):
        svc.archive("employees", emp["uid"], "archive", emp["version"])
    with pytest.raises(PeopleError):
        svc.save_employee(
            employee_data(emp, end_date=date.today()),
            uid=emp["uid"],
            expected_version=emp["version"],
        )
    overlap = f["absence"](emp)
    with pytest.raises(PeopleError) as conflict:
        act(svc, overlap, "submit")
    assert conflict.value.code == "overlap"
    with pytest.raises(PeopleError):
        act(svc, row, "cancel", note="")
    row = act(svc, row, "cancel", note="Plans changed")
    assert (
        row["state"] == "cancelled"
        and row["decision_by_uid"] == decided
        and row["decision_note"] == "Reviewed request"
        and row["cancellation_reason"] == "Plans changed"
    )
    overlap = act(svc, overlap, "submit")
    overlap = act(approver, overlap, "reject", note="Not available")
    assert overlap["state"] == "rejected"
    with pytest.raises(PeopleError):
        act(svc, overlap, "submit")


def test_concurrent_overlapping_submissions_one_wins(workforce):
    f = workforce
    svc = f["service"]
    emp = f["employee"]()
    a = f["absence"](emp)
    emp = svc.get("employees", emp["uid"])
    b = f["absence"](emp)
    version = svc.get("employees", emp["uid"])["version"]

    def submit(row):
        try:
            return act(svc, row, "submit", expected_employee_version=version)
        except PeopleError as exc:
            return exc

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(submit, [a, b]))
    assert sum(isinstance(x, dict) for x in results) == 1
    assert next(x for x in results if isinstance(x, PeopleError)).status == 409
    assert (
        svc.collection("absences", employee_uid=emp["uid"], state="submitted")["pageInfo"][
            "totalItems"
        ]
        == 1
    )


def test_validation_permissions_and_atomic_failure(workforce):
    f = workforce
    svc = f["service"]
    with pytest.raises(PeopleError):
        f["employee"](person_uid=f["issuer"]["uid"])
    with pytest.raises(ValidationError):
        f["employee"](start_date=date.today(), end_date=date.today() - timedelta(days=1))
    emp = f["employee"]()
    with pytest.raises(PeopleError):
        f["absence"](emp, start_date=date.today() - timedelta(days=366))
    reader = Service(svc.store, uuid4(), {"people.read"}, svc.dependencies)
    with pytest.raises(PeopleError) as denied:
        reader.save_employee(employee_data(emp), uid=emp["uid"], expected_version=1)
    assert denied.value.status == 403
    with pytest.raises(PeopleError):
        svc.transact(
            [
                svc.guard("employees", emp, 1, {"job_title": "Must roll back"}),
                svc.audit("employees", emp["uid"], "failed-fixture", 99, ["job_title"]),
                insert(Employee).values(uid=uuid4()),
            ]
        )
    assert svc.get("employees", emp["uid"])["job_title"] == "Consultant"
    assert not svc.store.read(
        select(AuditEvent.uid).where(
            AuditEvent.record_uid == UUID(emp["uid"]), AuditEvent.version == 99
        )
    )
    other_issuer = f["base_create"]("parties", kind="organization")
    company = f["base_create"](
        "operating-companies",
        party_uid=other_issuer["uid"],
        currency_uid=f["company"]["currency_uid"],
    )
    department = f["department"](operating_company_uid=company["uid"])
    with pytest.raises(PeopleError) as mismatch:
        svc.save_employee(
            employee_data(emp, department_uid=department["uid"]), uid=emp["uid"], expected_version=1
        )
    assert mismatch.value.code == "department"


def test_optional_staffing_authority_and_atomicity(workforce):
    from tests.erp.projects.conftest import business, project_services

    from src.erp.people.dependencies import Dependencies
    from src.erp.people.integrations import ProjectsPort
    from src.erp.projects.service import Service as ProjectsService

    f = workforce
    svc = f["service"]
    emp = f["employee"]()
    gen = business.__wrapped__(project_services.__wrapped__())
    p = next(gen)
    ps = p["service"]
    original = svc.dependencies
    try:
        project = p["new"](operating_company_uid=f["company"]["uid"])
        task = p["task"](project, assignee_party_uid=None)
        payload = {
            "expected_version": 1,
            "task_uid": task["uid"],
            "expected_task_version": task["version"],
            "expected_project_version": task["project_version"],
        }
        with pytest.raises(PeopleError) as missing:
            svc.staff(emp["uid"], payload)
        assert missing.value.code == "projects_unavailable"
        reader = ProjectsService(ps.store, ps.actor_uid, {"projects.read"}, ps.dependencies)
        svc.dependencies = Dependencies(f["base"], lambda: ProjectsPort(reader))
        with pytest.raises(PeopleError) as denied:
            svc.staff(emp["uid"], payload)
        assert denied.value.status == 403
        svc.dependencies = Dependencies(f["base"], lambda: ProjectsPort(ps))
        with pytest.raises(PeopleError):
            svc.staff(emp["uid"], {**payload, "expected_task_version": 99})
        assert (
            svc.get("employees", emp["uid"])["version"] == 1
            and ps.get("tasks", task["uid"])["assignee_party_uid"] is None
        )
        result = svc.staff(emp["uid"], payload)
        assert (
            result["task"]["assignee_party_uid"] == emp["person_uid"]
            and result["employee"]["version"] == 2
        )
        wrong = p["task"](p["new"]())
        with pytest.raises(PeopleError) as mismatch:
            svc.staff(
                emp["uid"],
                {
                    **payload,
                    "expected_version": 2,
                    "task_uid": wrong["uid"],
                    "expected_task_version": wrong["version"],
                    "expected_project_version": wrong["project_version"],
                },
            )
        assert mismatch.value.code == "company"
    finally:
        svc.dependencies = original
        try:
            next(gen)
        except StopIteration:
            pass


def test_http_contract_migration_isolation_and_restart(workforce):
    f = workforce
    emp = f["employee"]()
    identifiers = [
        "erp_base.alembic_version",
        "erp_projects.alembic_version",
        "erp_finance.alembic_version",
    ]
    before = {
        r.identifier: r.alembic_revision for r in MetaTable.filter(identifier__in=identifiers)
    }
    upgrade_application("src.erp.people.migrations:migration")
    after = {r.identifier: r.alembic_revision for r in MetaTable.filter(identifier__in=identifiers)}
    assert before == after and len(before) == 3
    code = """from metatables import configure_local_client
configure_local_client()
from src.erp.people.store import Store
from src.erp.people.service import Service
from api.erp.people.main import create_app
import sys,json
assert not any(k.startswith(('src.erp.crm','src.erp.projects','src.erp.finance','src.erp.sales','src.erp.catalog')) for k in sys.modules)
print(json.dumps(Service(Store(local_only=True),sys.argv[2],{'people.read'},None).get('employees',sys.argv[1])))
"""
    result = subprocess.run(
        [sys.executable, "-c", code, emp["uid"], str(f["service"].actor_uid)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["uid"] == emp["uid"]
    schemas = Path(__file__).parent / "contracts/sdk-0.5.19/schemas"
    documents = [json.loads(p.read_text()) for p in schemas.glob("*.json")]
    registry = Registry().with_resources([(d["$id"], Resource.from_contents(d)) for d in documents])
    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 54001)
    ) as client:
        assert client.get("/api/people/v1/ready/").json()["status"] == "ready"
        for resource in ["employees", "departments", "absences"]:
            for suffix, schema in [
                ("discovery/", "resource-discovery-v1"),
                ("", "resource-collection-v1"),
            ]:
                response = client.get(f"/api/people/v1/{resource}/{suffix}")
                assert response.status_code == 200, response.text
                Draft202012Validator(
                    json.loads((schemas / f"{schema}.schema.json").read_text()), registry=registry
                ).validate(response.json())
        assert (
            client.get("/api/people/v1/ready/", headers={"X-User-Uid": str(uuid4())}).status_code
            == 401
        )
        assert (
            client.get(
                "/api/people/v1/ready/", headers={"Origin": "https://foreign.invalid"}
            ).status_code
            == 403
        )
        assert (
            client.put(
                f"/api/people/v1/employees/{emp['uid']}/",
                json={**employee_data(emp), "expected_version": True},
            ).status_code
            == 422
        )
        assert client.get("/api/people/v1/employees/?page_size=101").status_code == 422
    from api.erp.people.main import create_app as application

    assert not any(
        getattr(route, "path", "").startswith("/api/people")
        for route in application(enabled=False).routes
    )
    original_optional = os.environ.get("PEOPLE_PROJECTS_ENABLED")
    os.environ["PEOPLE_PROJECTS_ENABLED"] = "false"
    try:
        with TestClient(
            create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 54002)
        ) as client:
            assert client.get("/api/people/v1/ready/").json()["projects_enabled"] is False
            assert client.get("/api/people/v1/employees/").status_code == 200
            assert client.get("/api/people/v1/references/tasks/").status_code == 503
    finally:
        if original_optional is None:
            os.environ.pop("PEOPLE_PROJECTS_ENABLED", None)
        else:
            os.environ["PEOPLE_PROJECTS_ENABLED"] = original_optional
    old = os.environ["PEOPLE_LOCAL_SOURCE_UID"]
    os.environ["PEOPLE_LOCAL_SOURCE_UID"] = str(uuid4())
    try:
        with pytest.raises(RuntimeError):
            create_app()
    finally:
        os.environ["PEOPLE_LOCAL_SOURCE_UID"] = old
