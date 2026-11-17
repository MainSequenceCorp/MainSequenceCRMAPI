"""Real local MetaTables integration: no mocked persistence or identity."""

from uuid import UUID

import pytest
from sqlalchemy import delete, select

from mainsequence.client import User
from metatables import configure_local_client, upgrade_application
from src.erp.base.metatables import Affiliation, AuditEvent, Party
from src.erp.base.service import BaseError
from src.erp.base.store import require_local_runtime
from src.erp.crm.base_adoption.commands import service
from src.erp.crm.base_adoption.reads import table
from src.erp.crm.base_adoption.resources import Resources
from src.erp.crm.base_adoption.store import Store
from src.erp.crm.platform.catalog import CatalogRegistry, configured_registry
from src.erp.crm.repositories.errors import ResourceConflict


@pytest.fixture
def context():
    configured_registry.cache_clear()
    configure_local_client()
    expected_source = str(require_local_runtime())
    upgrade_application("src.erp.base.migrations:migration")
    upgrade_application("src.erp.crm.migrations:migration")
    actor = User.get_authenticated_user_details().uid
    store = Store(CatalogRegistry())
    assert str(store.data_source_uid) == expected_source
    api = Resources(store)
    owned = []

    def create(resource, data, *, legacy=False):
        if legacy:
            from uuid import uuid4

            from sqlalchemy import insert

            from src.erp.crm.base_adoption.resources import common, typed_values
            from src.erp.crm.repositories.resources.writes import ResourceMutations

            t = table("contact" if resource == "contacts" else "company")
            uid = uuid4()
            values = {
                **common(uid, UUID(str(actor))),
                **typed_values(t, ResourceMutations._create_values(resource, data, actor)),
            }
            store.write([insert(t).values(**values)])
            row = api.reads.raw(resource, uid)
        else:
            row = api.create(resource, actor, data)
        owned.append((resource, UUID(row["uid"])))
        return row

    create.owned = owned
    yield store, api, service(store, actor), actor, create
    for resource, uid in reversed(owned):
        a = table("contact_company_affiliation")
        relationships = (
            store.read(select(a.c.uid).where(a.c.contact_uid == uid))
            if resource == "contacts"
            else []
        )
        for rel in relationships:
            rid = UUID(rel["uid"])
            store.write(
                [
                    delete(table("base_identity_link")).where(
                        table("base_identity_link").c.record_uid == rid
                    ),
                    delete(AuditEvent).where(AuditEvent.record_uid == rid),
                    delete(a).where(a.c.uid == rid),
                    delete(Affiliation).where(Affiliation.uid == rid),
                ]
            )
        steps = [
            delete(table("entity_redirect")).where(
                (table("entity_redirect").c.from_uid == uid)
                | (table("entity_redirect").c.to_uid == uid)
            ),
            delete(table("base_identity_link")).where(
                table("base_identity_link").c.record_uid == uid
            ),
            delete(AuditEvent).where(AuditEvent.record_uid == uid),
            delete(table("activity_event")).where(table("activity_event").c.entity_uid == uid),
        ]
        if resource == "contacts":
            steps.append(
                delete(table("contact_tag")).where(table("contact_tag").c.contact_uid == uid)
            )
        steps.extend(
            [
                delete(table("contact" if resource == "contacts" else "company")).where(
                    table("contact" if resource == "contacts" else "company").c.uid == uid
                ),
                delete(Party).where(Party.uid == uid),
            ]
        )
        store.write(steps)
    configured_registry.cache_clear()


def test_shared_identity_edits_preserve_profile_versions_and_affiliations(context):
    store, crm, base, actor, create = context
    company = create(
        "companies", {"name": "Local adoption organization", "country": "Unmapped source country"}
    )
    contact = create(
        "contacts",
        {
            "first_name": "Local",
            "last_name": "Adoption",
            "company_uid": company["uid"],
            "emails": [{"email": "adoption@example.com", "type": "work"}],
            "phones": [{"number": "123", "type": "home"}],
        },
    )
    party = base.get("parties", contact["uid"])
    assert party["emails"] == ["adoption@example.com"]
    assert party["identity"]["email_labels"] == {"adoption@example.com": "work"}
    assert base.get("parties", company["uid"])["identity"]["country"] == "Unmapped source country"
    payload = {
        k: party[k] for k in ("name", "kind", "emails", "phones", "identity", "language_uid")
    }
    payload["identity"]["first_name"] = "Changed"
    payload["name"] = "Changed Adoption"
    base.save("parties", payload, uid=party["uid"], expected_version=party["version"])
    updated = crm.reads.detail("contacts", contact["uid"])
    assert updated["first_name"] == "Changed" and updated["version"] == contact["version"] + 1
    with pytest.raises(ResourceConflict):
        crm.update("contacts", actor, contact["uid"], contact["version"], {"first_name": "Stale"})
    updated = crm.update(
        "contacts", actor, contact["uid"], updated["version"], {"first_name": "CRM edit"}
    )
    assert base.get("parties", contact["uid"])["identity"]["first_name"] == "CRM edit"
    with pytest.raises(BaseError, match="Archive the module"):
        base.archive("parties", contact["uid"], base.get("parties", contact["uid"])["version"])
    assert updated["company_uid"] == company["uid"]
    affiliations = store.read(
        select(Affiliation.__table__).where(Affiliation.person_uid == UUID(contact["uid"]))
    )
    assert len(affiliations) == 1 and affiliations[0]["organization_uid"] == company["uid"]


def test_partial_employment_dates_and_transition_rollback(context):
    from src.erp.crm.base_adoption.affiliations import Affiliations

    store, crm, base, actor, create = context
    company = create("companies", {"name": "First employer"})
    second = create("companies", {"name": "Second employer"})
    contact = create("contacts", {"first_name": "Employment fixture"})
    history = Affiliations(store)
    relationship = history.create_affiliation(
        actor,
        contact["uid"],
        {
            "company_uid": company["uid"],
            "status": "current",
            "is_primary": True,
            "started_period": "2020",
            "job_title": "Engineer",
            "expected_contact_version": contact["version"],
        },
    )
    shared = base.get("affiliations", relationship["uid"])
    assert shared["started_period"] == "2020" and shared["starts_on"] is None
    current = crm.reads.detail("contacts", contact["uid"])
    history.transition_company(
        actor,
        contact["uid"],
        {
            "expected_contact_version": current["version"],
            "previous_status": "former",
            "previous_ended_period": "2025-04",
            "new_company_uid": second["uid"],
            "new_started_period": "2025-05",
        },
    )
    shared = base.get("affiliations", relationship["uid"])
    assert (
        shared["ended_period"] == "2025-04"
        and shared["ends_on"] is None
        and shared["status"] == "former"
    )
    with pytest.raises(ResourceConflict):
        history.patch_affiliation(
            actor,
            contact["uid"],
            relationship["uid"],
            {
                "expected_version": relationship["version"],
                "expected_contact_version": current["version"],
                "changes": {"job_title": "Stale"},
            },
        )
    assert base.get("affiliations", relationship["uid"])["job_title"] == "Engineer"


def test_crm_merge_preserves_shared_identity_and_moves_only_owned_relationships(context):
    from src.erp.crm.base_adoption.merge import Merge

    store, crm, base, actor, create = context
    company = create("companies", {"name": "Merge organization"})
    survivor = create("contacts", {"first_name": "Merge survivor"})
    loser = create(
        "contacts",
        {
            "first_name": "Merge source",
            "company_uid": company["uid"],
            "emails": [{"email": "merge@example.com", "type": "work"}],
        },
    )
    merging = Merge(store)
    preview = merging.merge_preview(UUID(survivor["uid"]), UUID(loser["uid"]), {})
    result = merging.merge_contacts(
        actor,
        survivor["uid"],
        {
            "loser_uid": loser["uid"],
            "expected_version": survivor["version"],
            "loser_expected_version": loser["version"],
            "field_resolutions": {},
            "plan_hash": preview["plan_hash"],
        },
    )
    assert result["survivor"]["emails"] == loser["emails"]
    assert result["survivor"]["company_uid"] == company["uid"]
    assert "crm" not in base.get("parties", loser["uid"])["consumers"]
    relationships = store.read(
        select(Affiliation.__table__).where(Affiliation.person_uid == UUID(survivor["uid"]))
    )
    assert len(relationships) == 1


def test_controlled_extraction_repeat_collision_and_source_fences(context):

    from src.erp.crm.base_adoption.extraction import Extraction

    store, crm, base, actor, create = context
    contact = create(
        "contacts",
        {
            "first_name": "Historical fixture",
            "emails": [{"email": "historical@example.com", "type": "home"}],
            "created_by_uid": None,
        },
        legacy=True,
    )
    extraction = Extraction(store, actor, selection={"contacts": [contact["uid"]]})
    before = extraction.inventory()
    assert extraction.copy() == {"copied": 1, "unchanged": 0}
    assert extraction.copy() == {"copied": 0, "unchanged": 1}
    assert base.get("parties", contact["uid"])["provenance"]["created_by_uid"] is None
    assert extraction.activate(before)["contacts"] == 1
    updated = crm.update(
        "contacts", actor, contact["uid"], contact["version"], {"first_name": "After extraction"}
    )
    assert extraction.copy() == {"copied": 0, "unchanged": 1}
    assert base.get("parties", updated["uid"])["identity"]["first_name"] == "After extraction"
    with pytest.raises(ValueError, match="changed after"):
        extraction.activate(before)
    collision = create("contacts", {"first_name": "Collision source"}, legacy=True)
    steps, uid = base.plan_save(
        "parties",
        {"name": "Existing independent identity", "kind": "person"},
        create_uid=collision["uid"],
    )
    store.write(steps)
    with pytest.raises(ValueError, match="collision"):
        Extraction(store, actor, selection={"contacts": [collision["uid"]]}).copy()
    assert base.get("parties", collision["uid"])["name"] == "Existing independent identity"


def test_failed_profile_reference_rolls_back_base_identity(context):
    from uuid import uuid4

    store, crm, base, actor, create = context
    name = "Rollback " + uuid4().hex
    with pytest.raises(ResourceConflict):
        crm.create("contacts", actor, {"first_name": name, "tag_uids": [str(uuid4())]})
    assert not store.read(select(Party.uid).where(Party.name == name))
    assert not store.read(
        select(table("contact").c.uid).where(table("contact").c.first_name == name)
    )


def test_explicit_adoption_through_authenticated_local_http(context, monkeypatch):
    from fastapi.testclient import TestClient

    from api.erp.crm.local import create_app

    store, crm, base, actor, create = context
    person = base.save(
        "parties",
        {"name": "Directory HTTP fixture", "kind": "person", "emails": ["directory@example.com"]},
    )
    create.owned.append(("contacts", UUID(person["uid"])))
    monkeypatch.setenv("CRM_BASE_ADOPTION", "1")
    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 49001)
    ) as client:
        response = client.post(
            "/api/crm/v1/contacts/adopt/",
            json={"party_uid": person["uid"], "expected_party_version": person["version"]},
        )
        assert response.status_code == 201, response.text
        profile = response.json()
        assert profile["uid"] == person["uid"] and profile["first_name"] == person["name"]
        listing = client.get("/api/crm/v1/contacts/", params={"search": "Directory HTTP fixture"})
        assert listing.status_code == 200, listing.text
        assert listing.json()["items"][0]["uid"] == person["uid"]
        duplicate = client.post(
            "/api/crm/v1/contacts/adopt/",
            json={"party_uid": person["uid"], "expected_party_version": person["version"]},
        )
        assert duplicate.status_code == 409
        blocked = client.post(
            "/api/crm/v1/contacts/adopt/",
            json={"party_uid": person["uid"], "expected_party_version": person["version"]},
            headers={"x-user-id": str(actor)},
        )
        assert blocked.status_code == 401


def test_company_crm_edits_preserve_directory_contact_methods_and_other_fields(context):
    store, crm, base, actor, create = context
    company = create("companies", {"name": "Directory preservation fixture"})
    shared = base.get("parties", company["uid"])
    identity = {
        **shared["identity"],
        "email_labels": {"office@example.com": "work"},
        "socials": {"github": "https://github.com/example"},
    }
    shared = base.save(
        "parties",
        {"emails": ["office@example.com"], "phones": ["123"], "identity": identity},
        uid=shared["uid"],
        expected_version=shared["version"],
    )
    profile = crm.reads.detail("companies", company["uid"])
    crm.update("companies", actor, profile["uid"], profile["version"], {"name": "Updated company"})
    after = base.get("parties", shared["uid"])
    assert after["emails"] == ["office@example.com"] and after["phones"] == ["123"]
    assert after["identity"]["email_labels"] == identity["email_labels"]
    assert after["identity"]["socials"] == identity["socials"]


def test_base_exact_dates_and_partial_periods_remain_one_authority(context):
    from pydantic import ValidationError

    from src.erp.crm.base_adoption.affiliations import Affiliations

    store, crm, base, actor, create = context
    company = create("companies", {"name": "Period fixture"})
    person = create("contacts", {"first_name": "Period fixture"})
    history = Affiliations(store)
    relation = history.create_affiliation(
        actor,
        person["uid"],
        {
            "company_uid": company["uid"],
            "status": "former",
            "started_period": "2020",
            "ended_period": "2024",
            "expected_contact_version": person["version"],
        },
    )
    shared = base.get("affiliations", relation["uid"])
    shared = base.save(
        "affiliations",
        {"starts_on": "2020-03-02"},
        uid=shared["uid"],
        expected_version=shared["version"],
    )
    assert shared["started_period"] == shared["starts_on"] == "2020-03-02"
    assert (
        history.affiliation_detail(person["uid"], relation["uid"])["started_period"] == "2020-03-02"
    )
    shared = base.save(
        "affiliations",
        {"started_period": "2021-05"},
        uid=shared["uid"],
        expected_version=shared["version"],
    )
    assert shared["starts_on"] is None and shared["started_period"] == "2021-05"
    with pytest.raises(ValidationError, match="must agree"):
        base.save(
            "affiliations",
            {"starts_on": "2022-01-01", "started_period": "2020"},
            uid=shared["uid"],
            expected_version=shared["version"],
        )

    archived = base.archive("affiliations", shared["uid"], shared["version"])
    assert not archived["consumers"]["crm"]["active"]
    Store(CatalogRegistry(), require_active=True).data_source_uid
    restored = base.archive("affiliations", archived["uid"], archived["version"], restore=True)
    assert restored["consumers"]["crm"]["active"]
    Store(CatalogRegistry(), require_active=True).data_source_uid


def test_base_http_projects_and_preserves_unstructured_directory_names(context, monkeypatch):
    from fastapi.testclient import TestClient

    from api.erp.base.local import create_app

    store, crm, base, actor, create = context
    person = base.save("parties", {"name": "Full unsplit name", "kind": "person"})
    create.owned.append(("contacts", UUID(person["uid"])))
    profile = crm.adopt("contacts", actor, person["uid"], person["version"])
    crm.update(
        "contacts", actor, profile["uid"], profile["version"], {"title": "Business-only title"}
    )
    person = base.get("parties", person["uid"])
    assert person["identity"]["name_style"] == "unstructured"
    monkeypatch.setenv("CRM_BASE_ADOPTION", "1")
    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 49002)
    ) as client:
        # PUT's public contract still requires name/kind; the additional shared fields are optional.
        response = client.put(
            f"/api/base/v1/parties/{person['uid']}/",
            json={
                "name": "Changed full name",
                "kind": "person",
                "expected_version": person["version"],
            },
        )
        assert response.status_code == 200, response.text
    assert crm.reads.detail("contacts", person["uid"])["first_name"] == "Changed full name"


def test_google_storage_entrypoint_creates_base_identity_and_provenance_atomically(
    context, monkeypatch
):
    from datetime import datetime, timezone
    from uuid import uuid4

    from sqlalchemy import insert

    from src.erp.crm.base_adoption.resources import common, typed_values
    from src.erp.crm.google_workspace.store import GoogleStore

    store, crm, base, actor, create = context
    monkeypatch.setenv("CRM_BASE_ADOPTION", "1")
    source, connection = uuid4(), uuid4()
    source_table, oauth = table("source_connection"), table("google_oauth_connection")
    # This is storage fixture data; it contains no credential and performs no Google request.
    now = datetime.now(timezone.utc)
    store.write(
        [
            insert(source_table).values(
                **typed_values(source_table, common(source, UUID(str(actor)))),
                name="Local import fixture",
                adapter_id="google_workspace",
                source_account_key=str(source),
                configuration={},
            ),
            insert(oauth).values(
                uid=connection,
                actor_uid=UUID(str(actor)),
                source_connection_uid=source,
                google_sub=str(source),
                display_email="fixture@example.com",
                granted_scopes=[],
                refresh_ciphertext=None,
                status="connected",
                version=1,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    try:
        gateway = GoogleStore(store.registry)
        uid = gateway.import_candidate(
            actor_uid=actor,
            source_connection_uid=source,
            entity_type="contact",
            external_id="people/fixture",
            payload_hash="a" * 64,
            action="create",
            target_uid=None,
            expected_version=None,
            values={
                "first_name": "Imported fixture",
                "emails": [{"email": "imported@example.com", "type": "work"}],
            },
        )
        create.owned.append(("contacts", UUID(str(uid))))
        assert base.get("parties", uid)["emails"] == ["imported@example.com"]
        assert crm.reads.detail("contacts", uid)["first_name"] == "Imported fixture"
        rows = store.read(
            select(table("source_identity")).where(table("source_identity").c.target_uid == uid)
        )
        assert len(rows) == 1 and rows[0]["external_id"] == "people/fixture"
    finally:
        store.write(
            [
                delete(table("source_identity")).where(
                    table("source_identity").c.source_connection_uid == source
                ),
                delete(oauth).where(oauth.c.uid == connection),
                delete(source_table).where(source_table.c.uid == source),
            ]
        )


def test_merge_retains_notes_and_structured_interaction_participants(context):
    from datetime import datetime, timezone
    from uuid import uuid4

    from sqlalchemy import insert

    from src.erp.crm.base_adoption.merge import Merge
    from src.erp.crm.base_adoption.resources import common

    store, crm, base, actor, create = context
    survivor = create("contacts", {"first_name": "History survivor"})
    loser = create("contacts", {"first_name": "History loser"})
    note, interaction = uuid4(), uuid4()
    n, i = table("note"), table("interaction")
    now = datetime.now(timezone.utc)
    store.write(
        [
            insert(n).values(
                **common(note, UUID(str(actor))),
                contact_uid=UUID(loser["uid"]),
                text="Historical note",
                attachment_refs=[],
                occurred_at=now,
            ),
            insert(i).values(
                **common(interaction, UUID(str(actor))),
                subject="Historical conversation",
                kind="call",
                status="completed",
                participants=[
                    {"name": "Survivor", "contact_uid": survivor["uid"]},
                    {"name": "Loser", "contact_uid": loser["uid"]},
                    {"name": "Unlinked guest"},
                ],
            ),
        ]
    )
    try:
        merger = Merge(store)
        preview = merger._merge_plan(survivor["uid"], loser["uid"], {})
        merger.merge_contacts(
            actor,
            survivor["uid"],
            {
                "loser_uid": loser["uid"],
                "expected_version": survivor["version"],
                "loser_expected_version": loser["version"],
                "plan_hash": preview["plan_hash"],
                "field_resolutions": {},
            },
        )
        assert store.read(select(n).where(n.c.uid == note))[0]["contact_uid"] == survivor["uid"]
        participants = store.read(select(i).where(i.c.uid == interaction))[0]["participants"]
        assert participants == [
            {"name": "Survivor", "contact_uid": survivor["uid"]},
            {"name": "Unlinked guest"},
        ]
        Store(CatalogRegistry(), require_active=True).data_source_uid
    finally:
        store.write([delete(n).where(n.c.uid == note), delete(i).where(i.c.uid == interaction)])
