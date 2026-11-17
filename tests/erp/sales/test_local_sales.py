import json
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
from sqlalchemy import insert, select

from api.erp.sales.local import create_app
from metatables import MetaTable, upgrade_application
from src.erp.sales.errors import SalesError
from src.erp.sales.metatables import AuditEvent, Order
from src.erp.sales.schemas import OrderInput
from src.erp.sales.service import Service


def draft(row):
    result = {k: row[k] for k in OrderInput.model_fields if k != "lines"}
    result["lines"] = [
        {k: line[k] for k in ("item_uid", "description", "quantity", "unit_price", "discount")}
        for line in row["lines"]
    ]
    return result


def test_lifecycle_amounts_snapshots_and_permissions(business):
    svc = business["sales"]
    row = business["new"]()
    # The fixture uses a seeded currency; exact rounding follows that definition.
    from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

    c = business["currency"]
    expected = Decimal("33.750").quantize(
        Decimal(1).scaleb(-c["minor_units"]),
        rounding=ROUND_HALF_EVEN if c["rounding"] == "half_even" else ROUND_HALF_UP,
    )
    assert Decimal(row["net_total"]) == expected
    assert row["lines"][0]["snapshot"]["kind"] == "service"
    reader = Service(svc.store, svc.actor_uid, {"sales.read"}, svc.dependencies)
    assert reader.get(row["uid"])["uid"] == row["uid"]
    with pytest.raises(SalesError) as denied:
        reader.transition(row["uid"], "confirm", 1)
    assert denied.value.status == 403
    quoted = svc.transition(row["uid"], "quoted", 1)
    assert quoted["state"] == "quoted"
    with pytest.raises(SalesError):
        svc.save(draft(quoted), uid=row["uid"], expected_version=2)
    confirmed = svc.transition(row["uid"], "confirm", 2)
    assert confirmed["state"] == "confirmed" and confirmed["confirmed_at"]
    assert confirmed["lines"][0]["uid"] == row["lines"][0]["uid"]
    with pytest.raises(SalesError):
        svc.save(draft(confirmed), uid=row["uid"], expected_version=3)
    cancelled = svc.transition(row["uid"], "cancel", 3)
    reopened = svc.transition(row["uid"], "reopen", 4)
    assert cancelled["state"] == "cancelled" and reopened["state"] == "draft"
    assert (
        len(
            svc.store.read(
                select(AuditEvent.__table__).where(AuditEvent.record_uid == UUID(row["uid"]))
            )
        )
        == 5
    )


@pytest.mark.parametrize(
    "change",
    [
        {"quantity": "0"},
        {"quantity": "-1"},
        {"quantity": 1.0},
        {"unit_price": "NaN"},
        {"discount": "100.01"},
        {"unit_price": "-1"},
    ],
)
def test_strict_lines(business, change):
    p = business["payload"]
    p = {**p, "lines": [{**p["lines"][0], **change}]}
    with pytest.raises(ValidationError):
        business["sales"].save(p, request_uid=uuid4())


def test_expiry_empty_duplicate_and_unsaleable(business):
    svc = business["sales"]
    for row in [
        business["new"](valid_until=date.today() - timedelta(days=1)),
        business["new"](lines=[]),
    ]:
        with pytest.raises(SalesError) as invalid:
            svc.transition(row["uid"], "confirm", 1)
        assert invalid.value.status == 422
    first = business["new"]()
    with pytest.raises(SalesError) as duplicate:
        business["new"](name=first["name"])
    assert duplicate.value.status == 409
    item = business["item"]
    from src.erp.catalog.schemas import ItemInput

    business["catalog"].save(
        "items",
        {**{k: item[k] for k in ItemInput.model_fields}, "saleable": False},
        uid=item["uid"],
        expected_version=item["version"],
    )
    with pytest.raises(SalesError) as invalid:
        business["new"]()
    assert invalid.value.code == "not_saleable"


def test_concurrent_version_and_atomic_audit(business):
    svc = business["sales"]
    row = business["new"]()

    def edit(value):
        try:
            return svc.save({**draft(row), "notes": value}, uid=row["uid"], expected_version=1)
        except SalesError as exc:
            return exc

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(edit, ["first", "second"]))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert next(r for r in results if isinstance(r, SalesError)).status == 409
    assert svc.get(row["uid"])["version"] == 2
    # Force a transaction failure after audit insertion; nothing may commit.
    uid = uuid4()
    with pytest.raises(SalesError):
        svc.transact(
            [svc.audit(UUID(row["uid"]), "update", 99, ["notes"]), insert(Order).values(uid=uid)]
        )
    assert (
        len(
            svc.store.read(
                select(AuditEvent.__table__).where(AuditEvent.record_uid == UUID(row["uid"]))
            )
        )
        == 2
    )


def test_downstream_cancellation_guard(business):
    svc = business["sales"]
    row = business["new"]()
    svc.transition(row["uid"], "confirm", 1)
    linked = svc.attach(row["uid"], 2, "finance", uuid4())
    with pytest.raises(SalesError) as blocked:
        svc.transition(row["uid"], "cancel", linked["version"])
    assert blocked.value.code == "downstream_records"


def test_migration_restart_and_no_crm_import(business):
    row = business["new"]()
    ids = [
        "erp_base.alembic_version",
        "erp_catalog.alembic_version",
        "mainsequence_crm.alembic_version",
    ]
    before = {r.identifier: r.alembic_revision for r in MetaTable.filter(identifier__in=ids)}
    assert upgrade_application("src.erp.sales.migrations:migration")["revision"] == "0001"
    assert before == {
        r.identifier: r.alembic_revision for r in MetaTable.filter(identifier__in=ids)
    }
    code = """
from metatables import configure_local_client
configure_local_client()
from src.erp.sales.store import Store
from src.erp.sales.metatables import Order
from sqlalchemy import select
from uuid import UUID
import sys
from api.erp.sales.main import create_app
assert not any(k.startswith('src.erp.crm') for k in sys.modules)
assert not any(r.path.startswith('/api/sales') for r in create_app(enabled=False).routes)
print(Store(local_only=True).read(select(Order.__table__).where(Order.uid==UUID(sys.argv[1])))[0]['uid'])
"""
    out = subprocess.run(
        [sys.executable, "-c", code, row["uid"]], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == row["uid"]


def test_actual_http_identity_and_collection_contract(business):
    row = business["new"]()
    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 51000)
    ) as client:
        assert client.get("/api/sales/v1/ready/").json()["local"] is True
        for path, schema in [
            ("orders/", "resource-collection-v1"),
            ("orders/discovery/", "resource-discovery-v1"),
        ]:
            response = client.get("/api/sales/v1/" + path)
            assert response.status_code == 200, response.text
            schema = json.loads(
                (
                    Path("tests/erp/sales/contracts/sdk-0.5.19/schemas") / (schema + ".schema.json")
                ).read_text()
            )
            # The collection/discovery schemas use only local definitions on these responses.
            from referencing import Registry, Resource

            root = Path("tests/erp/sales/contracts/sdk-0.5.19/schemas")
            registry = Registry().with_resources(
                [
                    (
                        json.loads(p.read_text())["$id"],
                        Resource.from_contents(json.loads(p.read_text())),
                    )
                    for p in root.glob("*.json")
                ]
            )
            Draft202012Validator(schema, registry=registry).validate(response.json())
        detail = client.get("/api/sales/v1/orders/" + row["uid"] + "/")
        assert detail.status_code == 200
        assert (
            client.get("/api/sales/v1/ready/", headers={"x-user-uid": str(uuid4())}).status_code
            == 401
        )
        assert (
            client.get(
                "/api/sales/v1/ready/", headers={"Origin": "https://outside.example"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/sales/v1/orders/" + row["uid"] + "/confirm/", json={"expected_version": 0}
            ).status_code
            == 422
        )


def test_optional_crm_link_with_actual_adopted_company(business, monkeypatch):
    import httpx
    from sqlalchemy import delete

    from metatables import MetaTable
    from metatables.compiled_sql.v1 import compile_sqlalchemy_statement
    from src.erp.crm.base_adoption.reads import table
    from src.erp.crm.platform.catalog import configured_registry

    svc = business["sales"]
    customer = business["base"].get("parties", business["payload"]["customer_uid"])
    company_uid = UUID(customer["uid"])
    from datetime import datetime, timezone

    from sqlalchemy import update

    from src.erp.crm.base_adoption.resources import common, typed_values
    from src.erp.crm.base_adoption.store import Store as CrmStore

    configured_registry.cache_clear()
    fixture_store = CrmStore(configured_registry())
    assert str(fixture_store.data_source_uid) == str(svc.store.data_source_uid)
    pipeline_uid, stage_uid, deal_uid = uuid4(), uuid4(), uuid4()
    with httpx.Client(base_url="http://127.0.0.1:38641/api/crm/v1/", timeout=30) as client:
        try:
            adopted = client.post(
                "companies/adopt/",
                json={"party_uid": str(company_uid), "expected_party_version": customer["version"]},
            )
            assert adopted.status_code == 201, adopted.text
            assert adopted.json()["uid"] == str(company_uid)
            # Owned fixture setup uses governed statements. Legacy CRM board/write
            # SQL is PostgreSQL-specific; this verifies the actual published read
            # integration used by Sales, not CRM creation/board portability.
            fixture_name = "Sales link fixture " + uuid4().hex[:8]
            fixtures = [
                (
                    "pipeline",
                    pipeline_uid,
                    {"name": fixture_name, "is_default": False, "board_version": 1},
                ),
                (
                    "stage",
                    stage_uid,
                    {
                        "pipeline_uid": pipeline_uid,
                        "key": "fixture",
                        "label": "Fixture",
                        "position": 0,
                        "outcome": "open",
                        "is_active": True,
                    },
                ),
                (
                    "deal",
                    deal_uid,
                    {
                        "name": fixture_name,
                        "company_uid": company_uid,
                        "pipeline_uid": pipeline_uid,
                        "stage_uid": stage_uid,
                        "currency": business["currency"]["code"],
                        "position": 0,
                    },
                ),
            ]
            fixture_store.write(
                [
                    insert(table(key)).values(
                        **typed_values(table(key), {**common(uid, svc.actor_uid), **values})
                    )
                    for key, uid, values in fixtures
                ]
            )
            response = client.get(f"deals/{deal_uid}/")
            assert response.status_code == 200, response.text
            deal = response.json()
            row = business["new"](crm_deal_uid=deal["uid"])
            assert row["crm_deal_name"] == deal["name"]
            assert svc.transition(row["uid"], "confirm", 1)["state"] == "confirmed"
            with pytest.raises(SalesError) as mismatch:
                business["new"](
                    crm_deal_uid=deal["uid"],
                    customer_uid=business["base"].get(
                        "operating-companies", business["payload"]["operating_company_uid"]
                    )["party_uid"],
                )
            assert mismatch.value.code == "customer_mismatch"
            fixture_store.write(
                [
                    update(table("deal"))
                    .where(table("deal").c.uid == deal_uid)
                    .values(archived_at=datetime.now(timezone.utc), version=2)
                ]
            )
            with pytest.raises(SalesError) as inactive:
                business["new"](crm_deal_uid=deal["uid"])
            assert inactive.value.code == "inactive_opportunity"
            monkeypatch.setenv("SALES_CRM_ENABLED", "false")
            assert business["new"]()["state"] == "draft"
            with pytest.raises(SalesError) as unavailable:
                business["new"](crm_deal_uid=deal["uid"])
            assert unavailable.value.status == 503
        finally:
            # Remove only this test's disposable CRM records; business fixture owns Base/Sales.
            source = svc.store.data_source_uid
            steps = []
            if deal_uid:
                for key, field in [
                    ("activity_event", "entity_uid"),
                    ("deal_contact", "deal_uid"),
                    ("deal", "uid"),
                ]:
                    t = table(key)
                    steps.append(delete(t).where(t.c[field] == deal_uid))
            for key, uid in [("stage", stage_uid), ("pipeline", pipeline_uid)]:
                t = table(key)
                steps.append(delete(t).where(t.c.uid == uid))
            for key, field in [
                ("activity_event", "entity_uid"),
                ("base_identity_link", "record_uid"),
                ("company", "uid"),
            ]:
                t = table(key)
                steps.append(delete(t).where(t.c[field] == company_uid))
            for step in steps:
                MetaTable.execute_operation(
                    compile_sqlalchemy_statement(step, operation="delete", data_source_uid=source)
                )
