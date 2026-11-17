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
from src.erp.marketing.errors import MarketingError
from src.erp.marketing.metatables import AuditEvent, Mailing, Recipient
from src.erp.marketing.service import Service


def queue(svc, row):
    return svc.queue(
        row["uid"], {"expected_version": row["version"], "acknowledge_local_capture": True}
    )


def change(svc, sub, state):
    return svc.subscription(
        sub["uid"],
        {
            "expected_version": svc.get("subscribers", sub["uid"])["version"],
            "state": state,
            "evidence": "Local operator evidence",
        },
    )


def simulate(svc, recipient, kind):
    recipient = svc.get("recipients", recipient["uid"])
    return svc.simulate(
        recipient["uid"],
        {
            "expected_version": recipient["version"],
            "expected_mailing_version": recipient["mailing_version"],
            "kind": kind,
            "evidence": "Explicit simulation fixture",
        },
    )


def test_subscriptions_dedupe_and_frozen_audience(mailings):
    f = mailings
    svc = f["service"]
    party = f["person"]()
    sub = f["subscriber"](party)
    with pytest.raises(MarketingError) as duplicate:
        f["subscriber"](party)
    assert duplicate.value.status == 409
    with pytest.raises(MarketingError):
        f["subscriber"](party, email="wrong@example.com")
    with pytest.raises(ValidationError):
        f["subscriber"](party, created_by_uid=uuid4())
    row = f["mailing"]()
    result = f["add"](row, sub)
    row = result["mailing"]
    with pytest.raises(MarketingError):
        f["add"](row, sub)
    assert svc.get("mailings", row["uid"])["version"] == row["version"]
    with pytest.raises(ValidationError):
        svc.queue(row["uid"], {"expected_version": row["version"], "acknowledge_local_capture": 1})
    row = queue(svc, row)
    with pytest.raises(MarketingError):
        svc.mailing(
            {
                "name": row["name"],
                "subject": "changed",
                "body": "x",
                "sender_email": "p@example.com",
            },
            uid=row["uid"],
            expected_version=row["version"],
        )
    sub = change(svc, sub, "unsubscribed")
    row = svc.capture(row["uid"], row["version"])
    assert row["state"] == "completed" and row["results"] == {"suppressed": 1}
    recipient = svc.get("recipients", result["recipient"]["uid"])
    assert recipient["payload"] == {} and recipient["captured_at"] is None
    assert recipient["events"][0]["kind"] == "suppressed"
    change(svc, sub, "subscribed")


def test_capture_snapshot_and_simulated_engagement(mailings):
    f = mailings
    svc = f["service"]
    result = f["add"](f["mailing"](), f["subscriber"]())
    row = queue(svc, result["mailing"])
    row = svc.capture(row["uid"], row["version"])
    recipient = svc.get("recipients", result["recipient"]["uid"])
    assert (
        recipient["payload"]["body"] == "Owned capture fixture"
        and recipient["payload"]["mode"] == "local_capture"
    )
    for kind in ["opened", "clicked", "replied"]:
        recipient = simulate(svc, recipient, kind)
    with pytest.raises(MarketingError):
        simulate(svc, recipient, "replied")
    with pytest.raises(MarketingError):
        simulate(svc, recipient, "bounced")
    row = svc.get("mailings", row["uid"])
    assert row["simulated_engagement"] == {"opened": 1, "clicked": 1, "replied": 1}
    assert all(
        event["mode"] == "simulated" for event in recipient["events"] if event["kind"] != "captured"
    )
    assert "delivered" not in row and "sent" not in row


def test_bounded_batches_restart_and_cancel(mailings):
    f = mailings
    svc = f["service"]
    row = f["mailing"]()
    for _ in range(21):
        row = f["add"](row, f["subscriber"]())["mailing"]
    row = queue(svc, row)
    row = svc.capture(row["uid"], row["version"])
    assert row["state"] == "queued" and row["results"] == {"captured": 10, "pending": 11}
    code = """from metatables import configure_local_client
configure_local_client()
from src.erp.marketing.service import Service
from src.erp.marketing.store import Store
import json,sys
print(json.dumps(Service(Store(local_only=True),sys.argv[2],{'marketing.read'},None).get('mailings',sys.argv[1])))
"""
    result = subprocess.run(
        [sys.executable, "-c", code, row["uid"], str(svc.actor_uid)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["results"]["pending"] == 11
    row = svc.capture(row["uid"], row["version"])
    assert row["results"] == {"captured": 20, "pending": 1}
    row = svc.cancel(row["uid"], row["version"])
    assert row["results"] == {"captured": 20, "cancelled": 1} and row["state"] == "cancelled"
    assert len(svc.collection("recipients", mailing_uid=row["uid"], page_size=10)["items"]) == 10
    with pytest.raises(MarketingError):
        svc.capture(row["uid"], row["version"])


def test_competing_capture_and_atomic_failure(mailings):
    f = mailings
    svc = f["service"]
    result = f["add"](f["mailing"](), f["subscriber"]())
    row = queue(svc, result["mailing"])

    def run(_):
        try:
            return svc.capture(row["uid"], row["version"])
        except MarketingError as exc:
            return exc

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(run, range(2)))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert svc.get("mailings", row["uid"])["results"] == {"captured": 1}
    assert len(svc.events(result["recipient"]["uid"])["items"]) == 1
    saved = svc.get("mailings", row["uid"])
    with pytest.raises(MarketingError):
        svc.transact(
            [
                svc.guard(Mailing, saved, saved["version"], {"name": "Rollback"}),
                svc.audit("mailings", row["uid"], "failed-fixture", 99, []),
                insert(Recipient).values(uid=uuid4()),
            ]
        )
    assert svc.get("mailings", row["uid"])["name"] == row["name"]
    assert not svc.store.read(
        select(AuditEvent.uid).where(
            AuditEvent.record_uid == UUID(row["uid"]), AuditEvent.version == 99
        )
    )
    reader = Service(svc.store, uuid4(), {"marketing.read"}, svc.dependencies)
    with pytest.raises(MarketingError):
        reader.cancel(row["uid"], saved["version"])


def test_http_contracts_migration_independence(mailings, monkeypatch):
    from api.erp.marketing.local import create_app
    from api.erp.marketing.main import create_app as application

    row = mailings["mailing"]()
    ids = [
        "erp_base.alembic_version",
        "erp_collaboration.alembic_version",
        "src.erp.people.alembic_version",
    ]
    before = {r.identifier: r.alembic_revision for r in MetaTable.filter(identifier__in=ids)}
    upgrade_application("src.erp.marketing.migrations:migration")
    assert (
        before == {r.identifier: r.alembic_revision for r in MetaTable.filter(identifier__in=ids)}
        and len(before) == 3
    )
    code = """from api.erp.marketing.main import create_app
import sys
assert not any(k.startswith(('src.erp.crm','src.erp.collaboration','src.erp.projects','src.erp.people','src.erp.finance','src.erp.sales','src.erp.catalog')) for k in sys.modules)
"""
    subprocess.run([sys.executable, "-c", code], check=True)
    schemas = Path(__file__).parent / "contracts/sdk-0.5.19/schemas"
    documents = [json.loads(p.read_text()) for p in schemas.glob("*.json")]
    registry = Registry().with_resources([(d["$id"], Resource.from_contents(d)) for d in documents])
    monkeypatch.setenv("MARKETING_CRM_ENABLED", "false")
    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 55001)
    ) as client:
        root = "/api/marketing/v1"
        ready = client.get(root + "/ready/").json()
        assert ready["mode"] == "local_capture" and ready["crm_enabled"] is False
        for resource in ["mailings", "subscribers"]:
            for suffix, schema in [
                ("discovery/", "resource-discovery-v1"),
                ("", "resource-collection-v1"),
            ]:
                response = client.get(root + f"/{resource}/" + suffix)
                assert response.status_code == 200, response.text
                Draft202012Validator(
                    json.loads((schemas / f"{schema}.schema.json").read_text()), registry=registry
                ).validate(response.json())
        assert client.get(root + "/ready/", headers={"X-User-Uid": str(uuid4())}).status_code == 401
        assert (
            client.get(root + "/ready/", headers={"Origin": "https://foreign.invalid"}).status_code
            == 403
        )
        assert (
            client.post(
                root + f"/mailings/{row['uid']}/queue/",
                json={"expected_version": True, "acknowledge_local_capture": True},
            ).status_code
            == 422
        )
        assert client.get(root + "/mailings/?page_size=101").status_code == 422
    assert not any(
        getattr(route, "path", "").startswith(root) for route in application(enabled=False).routes
    )
    monkeypatch.setenv("MARKETING_LOCAL_SOURCE_UID", str(uuid4()))
    with pytest.raises(RuntimeError):
        create_app()


def test_unsubscribe_between_capture_read_and_commit_rolls_back(mailings, monkeypatch):
    from threading import Event

    f = mailings
    svc = f["service"]
    sub = f["subscriber"]()
    result = f["add"](f["mailing"](), sub)
    row = queue(svc, result["mailing"])
    reached, release = Event(), Event()
    original = svc.store.write

    def coordinated_write(steps):
        if len(steps) == 5:
            reached.set()
            assert release.wait(10)
        return original(steps)

    monkeypatch.setattr(svc.store, "write", coordinated_write)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(svc.capture, row["uid"], row["version"])
        try:
            assert reached.wait(10)
            change(svc, sub, "unsubscribed")
        finally:
            release.set()
        with pytest.raises(MarketingError) as conflict:
            future.result()
        assert conflict.value.status == 409
    monkeypatch.setattr(svc.store, "write", original)
    assert svc.get("mailings", row["uid"])["version"] == row["version"]
    assert svc.events(result["recipient"]["uid"])["items"] == []
    row = svc.capture(row["uid"], row["version"])
    assert row["results"] == {"suppressed": 1}


def test_optional_crm_followup_matches_adopted_person(mailings, monkeypatch):
    from tests.erp.marketing.crm_fixture import crm_followup_fixture

    f = mailings
    svc = f["service"]
    party = f["person"]()
    sub = f["subscriber"](party)
    with crm_followup_fixture(svc, party) as task:
        choices = svc.dependencies.tasks(party["uid"])
        assert [item["uid"] for item in choices["items"]] == [task["uid"]]
        result = f["add"](f["mailing"](), sub)
        row = queue(svc, result["mailing"])
        svc.capture(row["uid"], row["version"])
        recipient = simulate(svc, result["recipient"], "replied")
        payload = {
            "expected_version": recipient["version"],
            "expected_mailing_version": recipient["mailing_version"],
            "task_uid": task["uid"],
        }
        monkeypatch.setenv("MARKETING_CRM_ENABLED", "false")
        with pytest.raises(MarketingError) as missing:
            svc.link_followup(recipient["uid"], payload)
        assert missing.value.status == 503
        monkeypatch.setenv("MARKETING_CRM_ENABLED", "true")
        wrong = f["add"](f["mailing"](), f["subscriber"]())
        row = queue(svc, wrong["mailing"])
        svc.capture(row["uid"], row["version"])
        wrong = simulate(svc, wrong["recipient"], "replied")
        with pytest.raises(MarketingError) as mismatch:
            svc.link_followup(
                wrong["uid"],
                {
                    **payload,
                    "expected_version": wrong["version"],
                    "expected_mailing_version": wrong["mailing_version"],
                },
            )
        assert mismatch.value.status == 422
        linked = svc.link_followup(recipient["uid"], payload)
        assert linked["crm_task_uid"] == task["uid"]
        with pytest.raises(MarketingError):
            svc.link_followup(
                recipient["uid"],
                {
                    **payload,
                    "expected_version": linked["version"],
                    "expected_mailing_version": linked["mailing_version"],
                },
            )
