"""Shared API contract and SDK identity integration without storage or network writes."""

from importlib import import_module
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from api.erp.main import SETTINGS_PREFIX, create_app
from mainsequence.client import User
from mainsequence.server import fastapi as identity
from src.erp.modules import MODULES


def test_openapi_preserves_the_domain_path_and_method_inventory():
    application = create_app()
    paths = application.openapi()["paths"]
    local = application.state.mainsequence_request_identity["mode"] == "local"
    module_paths = {key: module.api_prefix for key, module in MODULES.items()}
    module_paths["user_preferences"] = SETTINGS_PREFIX
    for key, prefix in module_paths.items():
        factory = import_module(f"api.erp.{key}.main").create_app
        standalone = factory() if key == "crm" else factory(local=local)
        expected = {
            path: set(operations)
            for path, operations in standalone.openapi()["paths"].items()
            if path.startswith(prefix + "/")
        }
        composed = {
            path: set(operations)
            for path, operations in paths.items()
            if path.startswith(prefix + "/")
        }
        assert composed == expected


def test_shared_app_preserves_existing_google_and_campaign_paths():
    application = create_app()
    standalone = import_module("api.erp.crm.main").create_app()
    prefixes = ("/extensions/google/", "/extensions/campaigns/")
    expected = {
        path: set(operations)
        for path, operations in standalone.openapi()["paths"].items()
        if path.startswith(prefixes)
    }
    assert {
        path: set(operations)
        for path, operations in application.openapi()["paths"].items()
        if path.startswith(prefixes)
    } == expected
    assert "/extensions/campaigns/campaigns/" in expected
    public = {"/extensions/google/oauth/callback/", "/extensions/google/oauth/done/"}
    assert public <= {
        route.path for route in application.routes
        if isinstance(route, APIRoute) and "GET" in route.methods
    }


def test_shared_identity_and_module_admission_include_crm_mcp(monkeypatch):
    actor = identity.RequestUserIdentity(uid=str(uuid4()))
    source = uuid4()
    active = {"finance"}
    verification_calls = []
    policy_reads = []

    def verify(_endpoint, token):
        verification_calls.append(token)
        return actor

    def read_policy(_store, scope, **_options):
        assert scope == source
        assert User.get_logged_user().uid == actor.uid
        policy_reads.append(set(active))
        return {"version": 1, "active_module_keys": list(active)}

    monkeypatch.setenv("MAINSEQUENCE_ENDPOINT", "https://fixture.invalid")
    monkeypatch.setenv("ERP_USER_PREFERENCES_DATA_SOURCE_UID", str(source))
    monkeypatch.setenv("ERP_USER_PREFERENCES_PROVISIONED_MODULES", ",".join(MODULES))
    monkeypatch.setenv("FINANCE_SALES_ENABLED", "true")
    monkeypatch.setattr(identity, "_users_me", verify)
    monkeypatch.setattr("src.erp.user_preferences.admission.configured_store", lambda **_: object())
    monkeypatch.setattr("src.erp.user_preferences.admission.read_policy", read_policy)
    monkeypatch.setattr("api.erp.crm.main.solution_selling_enabled", lambda: True)

    auth = {"Authorization": "Bearer fixture"}
    mcp_headers = {
        **auth,
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-11-25",
    }
    mcp_list_tools = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    sales_discovery = "/api/sales/v1/orders/discovery/"
    with TestClient(create_app(local=True)) as client:
        assert client.get(sales_discovery).status_code == 401
        assert client.post("/mcp", json=mcp_list_tools).status_code == 401
        assert not verification_calls and not policy_reads

        denied = client.get(sales_discovery, headers=auth)
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "module_disabled"
        assert verification_calls == ["fixture"]

        # A Finance request cannot reopen an inactive Sales owner port.
        handoff = client.get("/api/finance/v1/references/orders/", headers=auth)
        assert handoff.status_code == 403
        assert handoff.json()["error"]["code"] == "module_disabled"

        # Settings and the shared API schema remain available while CRM is inactive.
        settings = client.get("/api/erp/v1/user-preferences/?unexpected=1", headers=auth)
        assert settings.status_code == 422
        assert settings.json()["error"]["code"] == "invalid_query"
        schema = client.get("/openapi.json", headers=auth)
        assert schema.status_code == 200
        assert sales_discovery in schema.json()["paths"]
        assert "/extensions/solution-selling/leads/" in schema.json()["paths"]
        assert len(policy_reads) == 2

        for path in ("/api/crm/v1/principals/", "/extensions/solution-selling/leads/"):
            denied = client.get(path, headers=auth)
            assert denied.status_code == 403
            assert denied.json()["error"]["code"] == "module_disabled"
            assert denied.json()["error"]["request_uid"]

        denied = client.post("/mcp", headers=mcp_headers, json=mcp_list_tools)
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "module_disabled"

        active.update({"crm", "catalog", "sales"})
        assert client.get(sales_discovery, headers=auth).status_code == 200
        mcp = client.post("/mcp", headers=mcp_headers, json=mcp_list_tools)
        assert mcp.status_code == 200
        assert any(tool["name"] == "crm_contacts_list" for tool in mcp.json()["result"]["tools"])
        assert "mcp-session-id" not in mcp.headers


def test_module_endpoints_cannot_become_public_through_dispatch(monkeypatch):
    monkeypatch.setenv(
        "FASTAPI_PUBLIC_INGRESS", '[{"method":"GET","path":"/api/sales/v1/ready/"}]'
    )
    with pytest.raises(RuntimeError, match="Public ingress route GET /api/sales/v1/ready/"):
        with TestClient(create_app()):
            pass


def test_shared_local_api_fails_closed_without_policy_configuration(monkeypatch):
    actor = identity.RequestUserIdentity(uid=str(uuid4()))
    monkeypatch.setenv("MAINSEQUENCE_ENDPOINT", "https://fixture.invalid")
    monkeypatch.setattr(identity, "_users_me", lambda *_: actor)
    for setting in (
        "ERP_USER_PREFERENCES_DATA_SOURCE_UID",
        "ERP_USER_PREFERENCES_LOCAL_SCOPE_UID",
        "ERP_USER_PREFERENCES_PROVISIONED_MODULES",
    ):
        monkeypatch.delenv(setting, raising=False)
    with TestClient(create_app(local=True), headers={"Authorization": "Bearer fixture"}) as client:
        for path in ("/api/crm/v1/principals/", "/api/sales/v1/orders/discovery/"):
            response = client.get(path)
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "module_policy_unavailable"
