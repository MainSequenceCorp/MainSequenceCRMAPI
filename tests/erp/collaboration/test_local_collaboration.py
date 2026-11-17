import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from referencing import Registry, Resource
from sqlalchemy import insert, select

from metatables import MetaTable, upgrade_application
from src.erp.collaboration.dependencies import Dependencies
from src.erp.collaboration.errors import CollaborationError
from src.erp.collaboration.integrations import ProjectsPort
from src.erp.collaboration.metatables import AuditEvent, Discussion, Message
from src.erp.collaboration.service import Service


def post(svc, row, body="First message", **changes):
    return svc.post(
        row["uid"],
        {
            "request_uid": uuid4(),
            "body": body,
            "expected_discussion_version": row["version"],
            **changes,
        },
    )


def command(result, **changes):
    return {
        "expected_version": result["message"]["version"],
        "expected_discussion_version": result["discussion"]["version"],
        **changes,
    }


def test_authorship_revisions_retraction_and_lifecycle(discussions):
    f = discussions
    svc = f["service"]
    row = f["new"]()
    result = post(svc, row, "Plain <script>alert(1)</script> text")
    mid = result["message"]["uid"]
    assert result["message"]["author_name"] == "Verified local author"
    reader = Service(svc.store, uuid4(), {"collaboration.read"}, svc.dependencies)
    moderator = Service(svc.store, uuid4(), svc.capabilities, svc.dependencies)
    with pytest.raises(CollaborationError):
        reader.revisions(mid)
    with pytest.raises(CollaborationError):
        post(reader, result["discussion"])
    with pytest.raises(CollaborationError):
        moderator.edit_message(mid, command(result, body="Impersonated"))
    result = svc.edit_message(mid, command(result, body="Corrected text"))
    history = svc.revisions(mid)["items"]
    assert [r["body"] for r in history] == [
        "Corrected text",
        "Plain <script>alert(1)</script> text",
    ]
    result = moderator.retract(mid, command(result, reason="Duplicate content"))
    assert reader.message(mid)["body"] == "" and reader.message(mid)["state"] == "retracted"
    assert svc.revisions(mid)["pageInfo"]["totalItems"] == 3
    with pytest.raises(CollaborationError):
        svc.edit_message(mid, command(result, body="Cannot restore"))
    row = result["discussion"]
    for action, state in [
        ("close", "closed"),
        ("archive", "archived"),
        ("restore", "closed"),
        ("reopen", "open"),
    ]:
        row = svc.transition(row["uid"], action, row["version"])
        assert row["state"] == state
        if state != "open":
            with pytest.raises(CollaborationError):
                post(svc, row)
    post(svc, row, "Follow-up")
    audit = svc.history(row["uid"])["items"]
    assert all("body" not in event["context"] for event in audit)


def test_atomicity_strict_validation_and_competing_posts(discussions):
    svc = discussions["service"]
    row = discussions["new"]()
    with pytest.raises(ValidationError):
        post(svc, row, author_name="Forged")
    with pytest.raises(ValidationError):
        post(svc, row, expected_discussion_version=True)
    with pytest.raises(ValidationError):
        discussions["new"](audience="authorized_project_readers")

    def attempt(_):
        try:
            return post(svc, row)
        except CollaborationError as exc:
            return exc

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert next(r for r in results if isinstance(r, CollaborationError)).status == 409
    row = svc.get(row["uid"])
    assert row["message_sequence"] == 1
    with pytest.raises(CollaborationError):
        svc.transact(
            [
                svc.guard(Discussion, row, row["version"], {"name": "Must roll back"}),
                svc.audit(row["uid"], "failed-fixture", 99, []),
                insert(Message).values(uid=uuid4()),
            ]
        )
    assert svc.get(row["uid"])["name"] == row["name"]
    assert not svc.store.read(
        select(AuditEvent.uid).where(
            AuditEvent.record_uid == UUID(row["uid"]), AuditEvent.version == 99
        )
    )
    mid = (
        results[0]["message"]["uid"]
        if isinstance(results[0], dict)
        else results[1]["message"]["uid"]
    )
    assert svc.revisions(mid)["pageInfo"]["totalItems"] == 1
    for i in range(26):
        result = post(svc, row, f"Message {i}")
        row = result["discussion"]
    page = svc.messages(row["uid"], page_size=25)
    assert page["pageInfo"]["hasNextPage"] and len(page["items"]) == 25
    older = svc.messages(row["uid"], page_index=1, page_size=25)
    assert len(older["items"]) == 2 and older["items"][-1]["sequence"] == 1


def test_project_audience_before_counts_and_revoked_owner_access(discussions):
    from tests.erp.projects.conftest import business, project_services

    from src.erp.projects.service import Service as ProjectsService

    f = discussions
    svc = f["service"]
    original = svc.dependencies
    gen = business.__wrapped__(project_services.__wrapped__())
    p = next(gen)
    ps = p["service"]
    try:
        project = p["new"]()
        other = p["new"]()
        with pytest.raises(CollaborationError):
            f["new"](
                scope="project", project_uid=project["uid"], audience="authorized_project_readers"
            )
        svc.dependencies = Dependencies(lambda: ProjectsPort(ps))
        row = f["new"](
            scope="project", project_uid=project["uid"], audience="authorized_project_readers"
        )
        result = post(svc, row)
        mid = result["message"]["uid"]
        assert svc.collection(search=row["name"])["pageInfo"]["totalItems"] == 0
        assert svc.collection(project_uid=other["uid"])["pageInfo"]["totalItems"] == 0
        assert svc.collection(project_uid=project["uid"])["pageInfo"]["totalItems"] == 1
        ps.capabilities.remove("projects.write")
        try:
            got = svc.get(row["uid"])
            assert not got["can_post"] and not got["can_manage"]
            with pytest.raises(CollaborationError):
                post(svc, result["discussion"])
        finally:
            ps.capabilities.add("projects.write")
        denied = ProjectsService(ps.store, ps.actor_uid, set(), ps.dependencies)
        svc.dependencies = Dependencies(lambda: ProjectsPort(denied))
        for operation in [
            lambda: svc.get(row["uid"]),
            lambda: svc.messages(row["uid"]),
            lambda: svc.revisions(mid),
            lambda: svc.history(row["uid"]),
            lambda: svc.collection(project_uid=project["uid"]),
            lambda: svc.transition(row["uid"], "close", 2),
        ]:
            with pytest.raises(CollaborationError) as exc:
                operation()
            assert exc.value.status == 404 and row["name"] not in exc.value.message
    finally:
        svc.dependencies = original
        try:
            next(gen)
        except StopIteration:
            pass


def test_http_contract_isolation_restart_and_disabled_integration(discussions, monkeypatch):
    from api.erp.collaboration.local import create_app
    from api.erp.collaboration.main import create_app as application

    row = discussions["new"]()
    svc = discussions["service"]
    ids = [
        "erp_base.alembic_version",
        "erp_projects.alembic_version",
        "src.erp.people.alembic_version",
    ]
    before = {r.identifier: r.alembic_revision for r in MetaTable.filter(identifier__in=ids)}
    upgrade_application("src.erp.collaboration.migrations:migration")
    assert (
        before == {r.identifier: r.alembic_revision for r in MetaTable.filter(identifier__in=ids)}
        and len(before) == 3
    )
    code = """from metatables import configure_local_client
configure_local_client()
from api.erp.collaboration.main import create_app
from src.erp.collaboration.service import Service
from src.erp.collaboration.store import Store
from src.erp.collaboration.dependencies import Dependencies
import sys,json
assert not any(k.startswith(('src.erp.crm','src.erp.base','src.erp.people','src.erp.projects','src.erp.finance','src.erp.sales','src.erp.catalog')) for k in sys.modules)
print(json.dumps(Service(Store(local_only=True),sys.argv[2],{'collaboration.read'},Dependencies()).get(sys.argv[1])))
"""
    result = subprocess.run(
        [sys.executable, "-c", code, row["uid"], str(svc.actor_uid)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["uid"] == row["uid"]
    schemas = Path(__file__).parent / "contracts/sdk-0.5.19/schemas"
    documents = [json.loads(p.read_text()) for p in schemas.glob("*.json")]
    registry = Registry().with_resources([(d["$id"], Resource.from_contents(d)) for d in documents])
    monkeypatch.setenv("COLLABORATION_PROJECTS_ENABLED", "false")
    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 54001)
    ) as client:
        root = "/api/collaboration/v1"
        ready = client.get(root + "/ready/").json()
        assert ready["projects_enabled"] is False and ready["actor_uid"] == str(svc.actor_uid)
        for suffix, schema in [
            ("discovery/", "resource-discovery-v1"),
            ("", "resource-collection-v1"),
        ]:
            response = client.get(root + "/discussions/" + suffix)
            assert response.status_code == 200, response.text
            Draft202012Validator(
                json.loads((schemas / f"{schema}.schema.json").read_text()), registry=registry
            ).validate(response.json())
        assert client.get(root + "/references/projects/").status_code == 503
        assert client.get(root + "/ready/", headers={"X-User-Uid": str(uuid4())}).status_code == 401
        assert (
            client.get(root + "/ready/", headers={"Origin": "https://foreign.invalid"}).status_code
            == 403
        )
        assert (
            client.post(
                root + f"/discussions/{row['uid']}/messages/",
                json={
                    "request_uid": str(uuid4()),
                    "body": "Test",
                    "author_uid": str(uuid4()),
                    "expected_discussion_version": 1,
                },
            ).status_code
            == 422
        )
        assert client.get(root + "/discussions/?page_size=101").status_code == 422
    assert not any(
        getattr(route, "path", "").startswith("/api/collaboration")
        for route in application(enabled=False).routes
    )
    monkeypatch.setenv("COLLABORATION_LOCAL_SOURCE_UID", str(uuid4()))
    with pytest.raises(RuntimeError):
        create_app()


def test_close_races_with_post_without_partial_message(discussions):
    svc = discussions["service"]
    row = discussions["new"]()

    def attempt(action):
        try:
            return (
                svc.transition(row["uid"], "close", row["version"])
                if action == "close"
                else post(svc, row)
            )
        except CollaborationError as exc:
            return exc

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(attempt, ["close", "post"]))
    assert sum(isinstance(result, dict) for result in results) == 1
    saved = svc.get(row["uid"])
    assert saved["version"] == 2
    assert saved["message_count"] == (1 if saved["state"] == "open" else 0)
    assert svc.history(row["uid"])["pageInfo"]["totalItems"] == 2
