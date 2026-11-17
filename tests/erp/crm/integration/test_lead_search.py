"""Run Lead search against owned PostgreSQL, including the submitted HTTP query."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from tests.erp.crm.integration import test_campaign_postgres as postgres_fixtures
from fastapi.testclient import TestClient

from api.erp.crm.main import create_app
from metatables import MetaTableCompiledSQLOperation
from src.erp.crm.metatables import MODELS
from src.erp.crm.repositories.records import VersionedRecordStore

lead_postgres = postgres_fixtures.campaign_postgres
collection_postgres = postgres_fixtures.collection_postgres


@pytest.fixture
def lead_search(lead_postgres, monkeypatch, signed_caller, config_file):
    actor = uuid.uuid4()
    now = datetime(2026, 11, 11, 9, tzinfo=UTC)
    with lead_postgres.connect() as db:
        transaction = db.begin()
        calls = []

        def execute(payload):
            MetaTableCompiledSQLOperation.model_validate(payload)
            calls.append(payload)
            rows = db.exec_driver_sql(
                payload["statement"]["sql"], payload["statement"]["parameters"],
            ).mappings().all()
            return {"rows": [dict(row) for row in rows]}

        monkeypatch.setattr("src.erp.crm.repositories.gateway.MetaTable.execute_operation", execute)
        store = VersionedRecordStore(SimpleNamespace(data_source_uid=str(uuid.uuid4())))
        common = {"version": 1, "created_at": now, "updated_at": now,
                  "created_by_uid": actor, "updated_by_uid": actor}
        companies = {}
        for name in ("Mobius Investments", "Whizpay", "Harbor Capital", "Literal_100%\\ Fund"):
            companies[name] = uuid.uuid4()
            db.execute(MODELS["company"].__table__.insert().values(
                **common, uid=companies[name], name=name, context_links=[],
            ))
        records = {}
        for index, (key, first, last, company, emails, status, notes, archived) in enumerate([
            ("nguyen", "Eric", "Nguyen", "Mobius Investments",
             [{"email": "eric@example.com"}, {"email": "research-alias@example.com"}], "contacted", None, False),
            ("karobia", "Eric", "Karobia", "Whizpay", [], "qualified", None, False),
            ("decoy", "Ada", "Lovelace", "Harbor Capital", [], "contacted", "A generic professional profile", False),
            ("companyless", "Alina", "Smith", None, [], "to_contact", None, False),
            ("unnamed", None, None, None, [{"email": "mail-only@example.com"}], "to_contact", None, False),
            ("literal", "Percy", "Literal", "Literal_100%\\ Fund", [], "to_contact", None, False),
            ("archived", "Eric", "Archived", None, [], "contacted", None, True),
        ]):
            contact_uid, uid = uuid.uuid4(), uuid.uuid4()
            db.execute(MODELS["contact"].__table__.insert().values(
                **common, uid=contact_uid, first_name=first, last_name=last,
                company_uid=companies.get(company), emails=emails, phones=[], socials={},
            ))
            db.execute(MODELS["solution_selling_lead"].__table__.insert().values(
                **{**common, "updated_at": now + timedelta(minutes=index)}, uid=uid,
                contact_uid=contact_uid, status=status, notes=notes,
                archived_at=now if archived else None,
            ))
            records[key] = str(uid)
        app = create_app()
        app.state.crm_record_store = store
        app.state.crm_policy = SimpleNamespace(capabilities=lambda uid: {"crm.read"} if uid == actor else set())
        app.state.crm_directory = object()
        try:
            with TestClient(app, headers=signed_caller(actor)) as client:
                yield SimpleNamespace(client=client, store=store, records=records, calls=calls)
        finally:
            transaction.rollback()


@pytest.mark.parametrize(("search", "expected"), [
    ("Eric", ["karobia", "nguyen"]),
    ("eRiC nGuYeN", ["nguyen"]),
    ("Nguyen", ["nguyen"]),
    ("MOBIUS", ["nguyen"]),
    ("RESEARCH-ALIAS", ["nguyen"]),
    ("Smith", ["companyless"]),
    ("mail-only@example.com", ["unnamed"]),
    ("%", ["literal"]),
    ("_", ["literal"]),
    ("\\", ["literal"]),
    ("generic", []),
    ("erci", []),
    ("' OR 1=1 --", []),
])
def test_search_matches_people_and_companies_not_hidden_notes(lead_search, search, expected):
    response = lead_search.client.get("/extensions/solution-selling/leads/", params={"search": search})
    assert response.status_code == 200, response.text
    data = response.json()
    assert [item["uid"] for item in data["items"]] == [lead_search.records[key] for key in expected]
    assert data["pageInfo"]["totalItems"] == len(expected)
    assert len(lead_search.calls) == 1


def test_matching_precedes_pagination_and_count(lead_search):
    pages = [lead_search.client.get("/extensions/solution-selling/leads/", params={
        "search": "Eric", "page_size": 1, "page_index": index,
    }).json() for index in range(3)]
    assert [item["uid"] for item in pages[0]["items"]] == [lead_search.records["karobia"]]
    assert [item["uid"] for item in pages[1]["items"]] == [lead_search.records["nguyen"]]
    assert pages[2]["items"] == []
    assert all(page["pageInfo"]["totalItems"] == 2 for page in pages)
    assert pages[0]["pageInfo"]["hasNextPage"] is True
    assert pages[1]["pageInfo"]["hasNextPage"] is False
    assert pages[1]["pageInfo"]["hasPreviousPage"] is True


def test_search_intersects_explicit_filters_and_leaves_unfiltered_list_complete(lead_search):
    filtered = lead_search.client.get("/extensions/solution-selling/leads/", params={
        "search": "Eric", "status": "contacted",
    }).json()
    assert [item["uid"] for item in filtered["items"]] == [lead_search.records["nguyen"]]
    assert filtered["pageInfo"]["totalItems"] == 1
    unfiltered = lead_search.client.get("/extensions/solution-selling/leads/").json()
    assert unfiltered["pageInfo"]["totalItems"] == 6
    assert lead_search.records["decoy"] in {item["uid"] for item in unfiltered["items"]}
