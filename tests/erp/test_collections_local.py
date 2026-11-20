"""Collection coverage through the real loopback ERP and governed SQLite."""

import os
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, update

from api.erp.local import create_app
from mainsequence.client import User
from metatables import MetaTable, configure_local_client, get_runtime_status
from src.erp.modules import MODULES, OPTIONAL_MODULES
from src.erp.user_preferences.metatables import MODELS, EnvironmentModuleActivation
from src.erp.user_preferences.service import Service
from src.erp.user_preferences.store import configured_store


@pytest.fixture
def erp_collections(monkeypatch):
    expected = os.environ.get("ERP_COLLECTION_LOCAL_SOURCE_UID")
    if not expected:
        pytest.skip("Set ERP_COLLECTION_LOCAL_SOURCE_UID to the disposable local DataSource")
    configure_local_client()
    runtime = get_runtime_status()
    assert runtime["local_mode"] is True and runtime["dialect"] == "sqlite"
    assert runtime["bootstrap"]["active"] and runtime["bootstrap"]["status"] == "ready"
    assert runtime["data_source"]["uid"] == expected and not runtime["data_source_error"]
    environment = uuid4()
    monkeypatch.setenv("ERP_USER_PREFERENCES_DATA_SOURCE_UID", expected)
    monkeypatch.setenv("ERP_USER_PREFERENCES_LOCAL_SCOPE_UID", str(environment))
    monkeypatch.setenv("ERP_USER_PREFERENCES_PROVISIONED_MODULES", ",".join(MODULES))
    monkeypatch.setenv("CRM_BASE_ADOPTION", "1")
    actor = User.get_authenticated_user_details()
    assert actor.is_active is True
    store = configured_store(local=True)
    assert str(store.data_source_uid) == expected
    Service(store, environment, UUID(str(actor.uid)), can_manage=True).seed(
        sorted(OPTIONAL_MODULES), set(MODULES)
    )
    try:
        yield store, environment
    finally:
        store.write(
            [
                delete(model.__table__).where(model.environment_uid == environment)
                for model in reversed(MODELS)
            ]
        )


def client():
    return TestClient(create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 49101))


def test_shared_erp_collection_routes(erp_collections, monkeypatch):
    executed = []
    execute = MetaTable.execute_operation

    def record(operation, **kwargs):
        if hasattr(operation, "statement"):
            executed.append(operation.statement.sql)
        else:
            executed.append(operation["statement"]["sql"])
        return execute(operation, **kwargs)

    monkeypatch.setattr(MetaTable, "execute_operation", record)
    with client() as http:
        # Establish the catalog and one-time adopted identity reconciliation.
        assert http.get("/api/crm/v1/contacts/").status_code == 200
        for path in (
            "/api/base/v1/parties/",
            "/api/catalog/v1/items/",
            "/api/crm/v1/contacts/",
            "/api/crm/v1/email-messages/",
            "/extensions/solution-selling/leads/",
            "/api/sales/v1/orders/",
            "/api/finance/v1/invoices/",
            "/api/projects/v1/projects/",
            "/api/people/v1/employees/",
            "/api/collaboration/v1/discussions/",
            "/api/marketing/v1/subscribers/",
            "/api/inventory/v1/balances/",
            "/api/purchasing/v1/orders/",
            "/api/manufacturing/v1/boms/",
            "/api/commerce/v1/sites/",
            "/api/reporting/v1/definitions/",
        ):
            executed.clear()
            response = http.get(path, params={"search": "zzq-collection-miss", "page_index": 3})
            assert response.status_code == 200, (path, response.json())
            assert response.json() == {
                "items": [],
                "pageInfo": {
                    "pageIndex": 3,
                    "pageSize": 25,
                    "totalItems": 0,
                    "hasNextPage": False,
                    "hasPreviousPage": True,
                },
            }
            if path.startswith("/api/base/"):
                assert len(executed) == 1
            elif not path.startswith("/api/collaboration/"):
                assert len(executed) == 1, path
                assert "erp_collection_decision" in executed[0], path
                assert response.headers["server-timing"].startswith("erp_collection_data;dur=")

        missing = uuid4()
        for path in (
            f"/api/projects/v1/tasks/{missing}/time/",
            f"/api/inventory/v1/balances/{missing}/audit/",
            f"/api/marketing/v1/subscribers/{missing}/audit/",
        ):
            executed.clear()
            response = http.get(path)
            assert response.status_code == 404, (path, response.json())
            assert len(executed) == 1 and "erp_visible_parent" in executed[0], path


def test_collection_checks_committed_policy_on_next_request(erp_collections, monkeypatch):
    store, environment = erp_collections
    path = "/api/finance/v1/invoices/"
    with client() as before, client() as after:
        assert before.get(path, params={"state": "invalid"}).status_code == 422
        assert after.get(path).status_code == 200
        policy = EnvironmentModuleActivation.__table__
        store.write(
            [
                update(policy)
                .where(policy.c.environment_uid == environment)
                .values(active_module_keys=[], version=policy.c.version + 1)
            ]
        )
        for query in ({"state": "posted"}, {"state": "invalid"}):
            denied = after.get(path, params=query)
            assert denied.status_code == 403
            assert denied.json()["error"]["code"] == "module_disabled"
        assert before.get("/api/base/v1/parties/").status_code == 200

        current_scope = policy.c.environment_uid == environment
        store.write(
            [update(policy).where(current_scope).values(active_module_keys=["finance", "finance"])]
        )
        unavailable = after.get(path)
        assert unavailable.status_code == 503
        assert unavailable.json()["error"]["code"] == "module_policy_unavailable"

        store.write(
            [
                update(policy)
                .where(current_scope)
                .values(active_module_keys=sorted(OPTIONAL_MODULES))
            ]
        )
        monkeypatch.setenv("ERP_USER_PREFERENCES_PROVISIONED_MODULES", "base")
        assert after.get(path).json()["error"]["code"] == "module_disabled"
        store.write([delete(policy).where(current_scope)])
        assert after.get(path).json()["error"]["code"] == "module_policy_unavailable"
