import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from api.erp.catalog.local import create_app
from api.erp.catalog.main import create_app as api_app
from api.erp.catalog.main import discovery
from metatables import MetaTable, upgrade_application
from src.erp.catalog.metatables import RESOURCES, AuditEvent
from src.erp.catalog.schemas import INPUTS, ConvertInput, UnitInput
from src.erp.catalog.service import CatalogError, Service
from src.erp.catalog.store import Store
from src.erp.modules import resolve_modules


def payload(resource, row, **changes):
    return {**{key: row[key] for key in INPUTS[resource].model_fields}, **changes}


def test_provider_independence_repeat_and_restart(catalog, quantities):
    before = {
        r.identifier: r.alembic_revision
        for r in MetaTable.filter(
            identifier__in=["erp_base.alembic_version", "mainsequence_crm.alembic_version"]
        )
    }
    assert upgrade_application("src.erp.catalog.migrations:migration")["revision"] == "0002"
    assert before == {
        r.identifier: r.alembic_revision for r in MetaTable.filter(identifier__in=list(before))
    }
    assert [m.key for m in resolve_modules(["catalog"])] == ["catalog"]
    code = """
import sys
from metatables import configure_local_client
configure_local_client()
from src.erp.catalog.store import Store
from src.erp.catalog.metatables import Item
from api.erp.catalog.main import create_app
from sqlalchemy import select
from uuid import UUID
assert not any(name.startswith(("src.erp.crm", "src.erp.base", "api.erp.crm")) for name in sys.modules)
assert not any(route.path.startswith("/api/catalog") for route in create_app(enabled=False).routes)
print(Store(local_only=True).read(select(Item.__table__).where(Item.uid == UUID(sys.argv[1])))[0]["uid"])
"""
    result = subprocess.run(
        [sys.executable, "-c", code, quantities[-1]["uid"]],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == quantities[-1]["uid"]


def test_crud_version_audit_unique_codes_and_permissions(catalog, quantities):
    item = quantities[-1]
    changed = catalog.save(
        "items",
        payload("items", item, name="Renamed local item"),
        uid=item["uid"],
        expected_version=1,
    )
    assert changed["name"] == "Renamed local item" and changed["version"] == 2
    with pytest.raises(CatalogError) as conflict:
        catalog.save("items", payload("items", item), uid=item["uid"], expected_version=1)
    assert conflict.value.status == 409
    with pytest.raises(CatalogError) as duplicate:
        catalog.save("items", payload("items", item))
    assert duplicate.value.status == 409
    events = catalog.store.read(
        select(AuditEvent.__table__).where(AuditEvent.record_uid == UUID(item["uid"]))
    )
    assert len(events) == 2 and {e["actor_uid"] for e in events} == {str(catalog.actor_uid)}
    reader = Service(catalog.store, catalog.actor_uid, {"catalog.read"})
    assert reader.get("items", item["uid"])["version"] == 2
    for operation in [
        lambda: reader.save("items", payload("items", item)),
        lambda: reader.archive("items", item["uid"], 2),
    ]:
        with pytest.raises(CatalogError) as denied:
            operation()
        assert denied.value.status == 403
    writer = Service(catalog.store, catalog.actor_uid, {"catalog.read", "catalog.write"})
    with pytest.raises(CatalogError):
        writer.save("unit-groups", {"name": "Denied", "code": "DENIED"})


def test_reference_lifecycle_and_atomic_rollback(catalog, quantities, records):
    group, reference, other, category, item = quantities
    for resource, row in [
        ("categories", category),
        ("unit-groups", group),
        ("units", reference),
        ("units", other),
    ]:
        with pytest.raises(CatalogError):
            catalog.archive(resource, row["uid"], row["version"])
        assert catalog.get(resource, row["uid"])["version"] == 1
        assert (
            len(
                catalog.store.read(
                    select(AuditEvent.uid).where(AuditEvent.record_uid == UUID(row["uid"]))
                )
            )
            == 1
        )
    catalog.archive("items", item["uid"], 1)
    catalog.archive("units", other["uid"], 1)
    catalog.archive("units", reference["uid"], 1)
    with pytest.raises(CatalogError):
        catalog.archive("units", other["uid"], 2, restore=True)
    with pytest.raises(CatalogError):
        catalog.archive("items", item["uid"], 2, restore=True)
    catalog.archive("units", reference["uid"], 2, restore=True)
    catalog.archive("units", other["uid"], 2, restore=True)
    assert catalog.archive("items", item["uid"], 2, restore=True)["version"] == 3
    blank = records("unit-groups")
    with pytest.raises(CatalogError):
        catalog.save(
            "units",
            {
                "name": "Must create reference first",
                "code": uuid4().hex.upper(),
                "group_uid": blank["uid"],
                "factor": "2",
            },
        )
    with pytest.raises(CatalogError):
        catalog.save("units", payload("units", reference, code=uuid4().hex.upper()))


def test_categories_cycle_leaf_move_and_archived_references(catalog, records):
    root = records("categories")
    child = records("categories", parent_uid=root["uid"])
    target = records("categories")
    with pytest.raises(CatalogError):
        catalog.save(
            "categories",
            payload("categories", root, parent_uid=child["uid"]),
            uid=root["uid"],
            expected_version=1,
        )
    with pytest.raises(CatalogError):
        catalog.save(
            "categories",
            payload("categories", root, parent_uid=target["uid"]),
            uid=root["uid"],
            expected_version=1,
        )
    moved = catalog.save(
        "categories",
        payload("categories", child, parent_uid=target["uid"]),
        uid=child["uid"],
        expected_version=1,
    )
    assert moved["parent_uid"] == target["uid"]
    catalog.archive("categories", root["uid"], 1)
    with pytest.raises(CatalogError):
        catalog.save(
            "categories",
            {"name": "Invalid", "code": uuid4().hex.upper(), "parent_uid": root["uid"]},
        )
    # Restore original parent relation for reverse-creation cleanup order.
    catalog.save(
        "categories",
        payload("categories", moved, parent_uid=None),
        uid=child["uid"],
        expected_version=2,
    )



def test_category_depth_limit(records):
    parent = None
    for depth in range(16):
        parent = records("categories", parent_uid=parent["uid"] if parent else None)
    with pytest.raises(CatalogError) as rejected:
        records("categories", parent_uid=parent["uid"])
    assert rejected.value.status == 422
    assert rejected.value.code == "invalid_parent"

def test_quantity_and_item_immutability_compatible_purchase_units(catalog, quantities, records):
    _, unit, _, _, item = quantities
    with pytest.raises(CatalogError) as frozen:
        catalog.save(
            "units",
            payload("units", unit, rounding_increment="0.1"),
            uid=unit["uid"],
            expected_version=1,
        )
    assert frozen.value.status == 422
    second_group = records("unit-groups")
    second = records("units", group_uid=second_group["uid"], is_reference=True)
    with pytest.raises(CatalogError) as incompatible:
        catalog.save(
            "items",
            payload("items", item, code=uuid4().hex.upper(), purchase_unit_uid=second["uid"]),
        )
    assert incompatible.value.status == 422
    with pytest.raises(CatalogError):
        catalog.save(
            "items", payload("items", item, kind="service"), uid=item["uid"], expected_version=1
        )
    service = records(
        "items",
        category_uid=item["category_uid"],
        unit_uid=unit["uid"],
        kind="service",
        purchase_description="Supplier description",
    )
    assert service["purchase_unit_uid"] == unit["uid"] and service["kind"] == "service"


@pytest.mark.parametrize(
    "quantity,rounding,expected",
    [
        ("1.025", "up", "1.05"),
        ("1.025", "half_up", "1.05"),
        ("1.025", "half_even", "1.00"),
        ("-1.025", "up", "-1.05"),
        ("-1.025", "half_even", "-1.00"),
        ("0", "up", "0.00"),
        ("1.05", "half_even", "1.05"),
    ],
)
def test_rounding_to_increment(catalog, quantities, quantity, rounding, expected):
    unit = quantities[1]
    result = catalog.convert(
        {
            "quantity": quantity,
            "from_unit_uid": unit["uid"],
            "to_unit_uid": unit["uid"],
            "rounding": rounding,
        }
    )
    assert result["quantity"] == expected


def test_conversion_ratio_rejects_other_groups_and_archived(catalog, quantities, records):
    _, unit, dozen, _, _ = quantities
    assert (
        catalog.convert(
            {"quantity": "2", "from_unit_uid": dozen["uid"], "to_unit_uid": unit["uid"]}
        )["quantity"]
        == "24.00"
    )
    assert (
        catalog.convert(
            {"quantity": "13", "from_unit_uid": unit["uid"], "to_unit_uid": dozen["uid"]}
        )["quantity"]
        == "2"
    )
    group = records("unit-groups")
    foreign = records("units", group_uid=group["uid"], is_reference=True)
    with pytest.raises(CatalogError):
        catalog.convert(
            {"quantity": "1", "from_unit_uid": foreign["uid"], "to_unit_uid": unit["uid"]}
        )
    catalog.archive("units", foreign["uid"], 1)
    with pytest.raises(CatalogError):
        catalog.convert(
            {"quantity": "1", "from_unit_uid": foreign["uid"], "to_unit_uid": foreign["uid"]}
        )


def test_competing_writers_one_wins(catalog, quantities):
    item = quantities[-1]

    def change(n):
        try:
            return catalog.save(
                "items",
                payload("items", item, description=f"Writer {n}"),
                uid=item["uid"],
                expected_version=1,
            )["version"]
        except CatalogError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(change, [1, 2])) == [2, 409]


@pytest.mark.parametrize(
    "value", ["NaN", "Infinity", "1e4", "-1", "0", 0.1, True, "1.0000000000001"]
)
def test_strict_decimal_contract(value):
    with pytest.raises(ValidationError):
        UnitInput(name="Invalid", code="INVALID", group_uid=uuid4(), factor=value)
    with pytest.raises(ValidationError):
        ConvertInput(quantity=1.2, from_unit_uid=uuid4(), to_unit_uid=uuid4())


def test_real_http_identity_queries_contracts(catalog, quantities):
    item = quantities[-1]
    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 49000)
    ) as client:
        ready = client.get("/api/catalog/v1/ready/")
        assert ready.status_code == 200 and ready.json()["schema_revision"] == "0002"
        assert ready.json()["data_source_uid"] == os.environ["CATALOG_LOCAL_SOURCE_UID"]
        assert client.get("/api/catalog/v1/items/discovery/").json() == discovery("items")
        for path in [
            "items/?unknown=true",
            "items/?page_size=101",
            "units/?kind=product",
            "items/discovery/?page_size=5",
        ]:
            assert client.get("/api/catalog/v1/" + path).status_code == 422
        result = client.get(
            "/api/catalog/v1/items/",
            params={"search": item["code"], "kind": "product", "page_size": 1},
        ).json()
        assert result["items"][0]["uid"] == item["uid"] and result["pageInfo"]["totalItems"] == 1
        assert (
            client.get("/api/catalog/v1/ready/", headers={"X-User-UID": item["uid"]}).status_code
            == 401
        )
        assert (
            client.get(
                "/api/catalog/v1/ready/", headers={"Origin": "https://foreign.example"}
            ).status_code
            == 403
        )
        response = client.put(
            f"/api/catalog/v1/items/{item['uid']}/",
            json={**payload("items", item, name="HTTP updated"), "expected_version": 1},
        )
        assert response.status_code == 200 and response.json()["version"] == 2
    with TestClient(api_app()) as client:
        assert client.get("/api/catalog/v1/items/").status_code == 401


def test_sdk_discovery_and_collection_schema(catalog):
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    contracts = Path(__file__).parent / "contracts/sdk-0.5.19"
    manifest = json.loads((contracts / "manifest.json").read_text())
    registry = Registry()
    for entry in manifest["schemas"]:
        schema = json.loads((contracts / entry["file"]).read_text())
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    for entry in manifest["schemas"]:
        if entry["contract"] not in {
            "command-center.resource_discovery@v1",
            "command-center.resource_collection@v1",
        }:
            continue
        validator = Draft202012Validator(
            json.loads((contracts / entry["file"]).read_text()), registry=registry
        )
        for resource in RESOURCES:
            validator.validate(
                discovery(resource)
                if "discovery" in entry["contract"]
                else catalog.collection(resource)
            )


def test_local_source_fail_closed(monkeypatch):
    import src.erp.catalog.store as module

    monkeypatch.setattr(
        module, "get_runtime_status", lambda: {"local_mode": False, "dialect": "postgresql"}
    )
    with pytest.raises(RuntimeError):
        Store(local_only=True).write([])
