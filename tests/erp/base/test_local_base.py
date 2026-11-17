import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from api.erp.base.local import create_app
from api.erp.base.main import create_app as hosted_app
from api.erp.base.main import discovery
from metatables import upgrade_application
from src.erp.base.metatables import RESOURCES, AuditEvent
from src.erp.base.schemas import AffiliationInput, PartyInput, PreferenceInput, RoundInput
from src.erp.base.seed import seed
from src.erp.base.service import BaseError, Service
from src.erp.modules import resolve_modules


def party(name="Local Base fixture", kind="person"):
    return {"name": name, "kind": kind, "emails": [], "phones": []}


def test_repeat_migrations_seed_and_provider_isolation(base_service):
    from src.erp.base.migrations import migration

    result = upgrade_application("src.erp.base.migrations:migration")
    assert result["revision"] == "0001"
    assert seed(base_service) == {"countries": 0, "languages": 0, "currencies": 0}
    assert all(
        table.name.startswith("erp_base__") for table in migration.target_metadata.tables.values()
    )
    assert all("crm" not in model.__module__ for model in RESOURCES.values())
    assert resolve_modules([]) == ()
    with pytest.raises(ValueError):
        resolve_modules(["crm"])


def test_crud_stale_version_audit_archive_and_restart(base_service, records):
    item = records("parties", party())
    edited = base_service.save(
        "parties", party("Updated Base fixture"), uid=item["uid"], expected_version=1
    )
    assert edited["version"] == 2
    with pytest.raises(BaseError, match="changed") as conflict:
        base_service.save("parties", party("Lost update"), uid=item["uid"], expected_version=1)
    assert conflict.value.status == 409
    events = base_service.store.read(
        select(AuditEvent.__table__).where(AuditEvent.record_uid == UUID(item["uid"]))
    )
    assert len(events) == 2
    archived = base_service.archive("parties", item["uid"], 2)
    assert archived["version"] == 3 and archived["archived_at"]
    assert not base_service.archive("parties", item["uid"], 3, restore=True)["archived_at"]
    code = "from metatables import configure_local_client; configure_local_client(); from src.erp.base.store import Store; from src.erp.base.metatables import Party; from sqlalchemy import select; from uuid import UUID; import sys; print(Store(local_only=True).read(select(Party.__table__).where(Party.uid == UUID(sys.argv[1])))[0]['name'])"
    result = subprocess.run(
        [sys.executable, "-c", code, item["uid"]], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "Updated Base fixture"


def test_reference_guards_and_archive_rollback(base_service, records):
    person = records("parties", party())
    org = records("parties", party("Local organization", "organization"))
    link = records(
        "affiliations",
        {
            "name": "Employment",
            "person_uid": person["uid"],
            "organization_uid": org["uid"],
            "role": "Engineer",
        },
    )
    with pytest.raises(BaseError):
        base_service.archive("parties", org["uid"], 1)
    assert base_service.get("parties", org["uid"])["version"] == 1
    with pytest.raises(BaseError):
        base_service.save(
            "affiliations",
            {
                "name": "Wrong kinds",
                "person_uid": org["uid"],
                "organization_uid": person["uid"],
                "role": "Engineer",
            },
        )
    base_service.archive("affiliations", link["uid"], 1)
    base_service.archive("parties", org["uid"], 1)
    with pytest.raises(BaseError):
        base_service.archive("affiliations", link["uid"], 2, restore=True)
    assert base_service.get("affiliations", link["uid"])["version"] == 2


def test_geography_currency_company_and_cycle(base_service, records):
    countries = {item["code"]: item for item in base_service.collection("countries")["items"]}
    currency = next(
        item for item in base_service.collection("currencies")["items"] if item["code"] == "EUR"
    )
    subdivision = records(
        "subdivisions",
        {
            "name": "Local subdivision",
            "code": "AT-" + uuid4().hex[:8].upper(),
            "country_uid": countries["AT"]["uid"],
        },
    )
    org = records("parties", party("Local operating organization", "organization"))
    company = records(
        "operating-companies",
        {
            "name": "Local operating company",
            "party_uid": org["uid"],
            "currency_uid": currency["uid"],
        },
    )
    with pytest.raises(BaseError, match="acyclic"):
        base_service.save(
            "operating-companies",
            {
                "name": company["name"],
                "party_uid": org["uid"],
                "currency_uid": currency["uid"],
                "parent_uid": company["uid"],
            },
            uid=company["uid"],
            expected_version=1,
        )
    with pytest.raises(BaseError):
        base_service.save(
            "addresses",
            {
                "name": "Wrong country",
                "party_uid": org["uid"],
                "country_uid": countries["DE"]["uid"],
                "subdivision_uid": subdivision["uid"],
                "street": "Test street",
                "city": "Test",
            },
        )
    address = records(
        "addresses",
        {
            "name": "Office",
            "party_uid": org["uid"],
            "country_uid": countries["AT"]["uid"],
            "subdivision_uid": subdivision["uid"],
            "street": "Test street",
            "city": "Vienna",
        },
    )
    assert address["country_uid"] == countries["AT"]["uid"]
    assert base_service.round_amount(currency["uid"], "2.345")["amount"] == "2.34"
    assert base_service.round_amount(currency["uid"], "-2.355")["amount"] == "-2.36"


def test_number_allocation_retry_and_concurrent_edit(base_service, records):
    sequence = records(
        "number-sequences",
        {"name": "Local sequence", "code": "test_" + uuid4().hex, "prefix": "TEST-", "padding": 4},
    )
    request = uuid4()
    result = base_service.allocate(sequence["uid"], request, 1)
    assert result["value"] == "TEST-0001"
    assert base_service.allocate(sequence["uid"], request, 1) == result

    def allocate(_):
        try:
            return base_service.allocate(sequence["uid"], uuid4(), 2)
        except BaseError as error:
            assert error.status == 409
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outputs = list(pool.map(allocate, [0, 1]))
    assert sum(output is not None for output in outputs) == 1
    assert base_service.get("number-sequences", sequence["uid"])["next_number"] == 3


def test_same_allocation_request_is_safe_when_concurrent(base_service, records):
    sequence = records(
        "number-sequences",
        {"name": "Retry sequence", "code": "retry_" + uuid4().hex, "prefix": "RETRY-"},
    )
    request = uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        outputs = list(
            pool.map(lambda _: base_service.allocate(sequence["uid"], request, 1), [0, 1])
        )
    assert outputs[0] == outputs[1]
    assert base_service.get("number-sequences", sequence["uid"])["next_number"] == 2
    events = base_service.store.read(
        select(AuditEvent.__table__).where(AuditEvent.record_uid == UUID(sequence["uid"]))
    )
    assert len(events) == 2  # Creation and one allocation, despite two callers.


def test_permissions_and_private_preferences(base_service, records):
    stranger = Service(base_service.store, uuid4(), {"base.read"})
    with pytest.raises(BaseError) as denied:
        stranger.save("parties", party())
    assert denied.value.status == 403
    no_access = Service(base_service.store, uuid4(), set())
    with pytest.raises(BaseError):
        no_access.collection("countries")
    # A disposable platform-actor UUID verifies service scoping only; no identity
    # middleware is mocked or claimed to have authenticated this fixture actor.
    saved = stranger.save("preferences", {"timezone": "Europe/Vienna"})
    try:
        assert stranger.get("preferences", saved["uid"])["timezone"] == "Europe/Vienna"
        with pytest.raises(BaseError) as hidden:
            base_service.get("preferences", saved["uid"])
        assert hidden.value.status == 404
    finally:
        from sqlalchemy import delete

        base_service.store.write(
            [
                delete(AuditEvent.__table__).where(AuditEvent.record_uid == UUID(saved["uid"])),
                delete(RESOURCES["preferences"].__table__).where(
                    RESOURCES["preferences"].uid == UUID(saved["uid"])
                ),
            ]
        )


@pytest.mark.parametrize(
    "model,payload",
    [
        (PartyInput, {"name": " ", "kind": "person"}),
        (PartyInput, {"name": "x", "kind": "person", "owner_uid": str(uuid4())}),
        (PartyInput, {"name": "x", "kind": "person", "emails": ["bad"]}),
        (PreferenceInput, {"timezone": "not/a-zone"}),
        (
            AffiliationInput,
            {
                "name": "x",
                "person_uid": uuid4(),
                "organization_uid": uuid4(),
                "role": "x",
                "starts_on": "2026-02-02",
                "ends_on": "2026-01-01",
            },
        ),
        (RoundInput, {"amount": "NaN"}),
    ],
)
def test_strict_input_validation(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_local_http_identity_discovery_and_validation(base_service, records):
    row = records("parties", party("HTTP fixture"))
    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 49000)
    ) as client:
        assert client.get("/api/base/v1/ready/").json()["local"] is True
        response = client.get("/api/base/v1/parties/discovery/")
        assert response.json() == discovery("parties")
        assert client.get("/api/base/v1/parties/discovery/?page_size=2").status_code == 422
        assert client.get("/api/base/v1/parties/?page_size=101").status_code == 422
        assert client.get(f"/api/base/v1/parties/{row['uid']}/").json()["name"] == "HTTP fixture"
        assert (
            client.post(
                "/api/base/v1/parties/", json={"name": "x", "kind": "person", "version": 99}
            ).status_code
            == 422
        )
        assert (
            client.get(
                "/api/base/v1/ready/", headers={"Origin": "https://evil.example"}
            ).status_code
            == 403
        )
        assert (
            client.get("/api/base/v1/ready/", headers={"X-User-UID": row["uid"]}).status_code == 401
        )
    with TestClient(hosted_app(), base_url="http://127.0.0.1") as client:
        assert client.get("/api/base/v1/parties/").status_code == 401
    app = hosted_app(enabled=False)
    assert all(not route.path.startswith("/api/base") for route in app.routes)


def test_sdk_collection_and_discovery_contracts(base_service):
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
        for path in entry["fixtures"]["valid"]:
            validator.validate(json.loads((contracts / path).read_text()))
        for path in entry["fixtures"]["invalid"]:
            assert list(validator.iter_errors(json.loads((contracts / path).read_text())))
        for resource in RESOURCES:
            validator.validate(
                discovery(resource)
                if "discovery" in entry["contract"]
                else base_service.collection(resource)
            )


def test_unique_codes_and_immutable_identity(base_service, records):
    currency = next(
        row for row in base_service.collection("currencies")["items"] if row["code"] == "EUR"
    )
    with pytest.raises(BaseError) as duplicate:
        base_service.save(
            "currencies", {"name": "Duplicate", "code": "EUR", "symbol": "€", "minor_units": 2}
        )
    assert duplicate.value.status == 409
    row = records("parties", party())
    with pytest.raises(BaseError) as immutable:
        base_service.save("parties", party(kind="organization"), uid=row["uid"], expected_version=1)
    assert immutable.value.status == 422
    assert base_service.get("currencies", currency["uid"])["name"] == currency["name"]


def test_wrong_runtime_is_rejected_before_writes(monkeypatch):
    import src.erp.base.store as store_module

    monkeypatch.setattr(
        store_module, "get_runtime_status", lambda: {"local_mode": False, "dialect": "postgresql"}
    )
    with pytest.raises(RuntimeError, match="local SQLite"):
        store_module.Store(local_only=True).write([])


def test_base_imports_without_crm():
    code = """
import sys
from api.erp.base.main import create_app
from src.erp.base.migrations import migration
assert not any(name == "src.crm" or name.startswith(("src.crm.", "src.erp.crm", "api.erp.crm")) for name in sys.modules)
assert not any(route.path.startswith("/api/base") for route in create_app(enabled=False).routes)
print("Base independent")
"""
    result = subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True
    )
    assert result.stdout.strip() == "Base independent"
