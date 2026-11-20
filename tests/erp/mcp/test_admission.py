"""Exercise the shared endpoint with SDK-verified test assertions."""

import hashlib
from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient
from tests.erp.crm.agent.test_mcp_tools import ACTOR, AGENT, delegated
from tests.erp.crm.conftest import hosted_crm_activation, signed_caller  # noqa: F401

from api.erp.main import create_app
from mainsequence.client import User

MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "MCP-Protocol-Version": "2025-11-25",
}


def test_shared_catalogue_uses_the_verified_person(signed_caller, monkeypatch):  # noqa: F811
    active = ["catalog"]
    capabilities_for_actor = {"base.read", "catalog.read", "catalog.write"}
    directory_calls = []

    def profile(uid):
        directory_calls.append(uid)
        return SimpleNamespace(
            uid=uid, is_active=True, identity_type="workload" if uid == str(AGENT) else "human"
        )

    def capabilities(*, local):
        assert not local
        person = User.get_requester() or User.get_logged_user()
        assert person.uid == str(ACTOR)
        return UUID(person.uid), capabilities_for_actor

    monkeypatch.setenv("ERP_USER_PREFERENCES_PROVISIONED_MODULES", "base,catalog,crm")
    monkeypatch.setattr(User, "get_by_uid", profile)
    for module in ("base", "catalog"):
        monkeypatch.setattr(f"api.erp.{module}.identity.actor_and_capabilities", capabilities)
    monkeypatch.setattr("api.erp.user_preferences.main.configured_store", lambda **_: object())
    monkeypatch.setattr(
        "src.erp.user_preferences.service.read_policy",
        lambda *_: {"version": 1, "active_module_keys": active},
    )
    monkeypatch.setattr(
        "api.erp.user_preferences.main.ready_modules", lambda *_, candidates, **__: candidates
    )

    with TestClient(create_app(), base_url="https://crm.example.test") as client:

        def rpc(auth, method, params):
            response = client.post(
                "/mcp",
                headers={**MCP_HEADERS, **auth},
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            )
            assert response.status_code == 200
            return response.json()

        direct = signed_caller(ACTOR)
        on_behalf_of = delegated(signed_caller)
        for auth in (direct, on_behalf_of):
            listed = rpc(auth, "tools/list", {})
            visible = {tool["name"] for tool in listed["result"]["tools"]}
            assert "base_parties_list" in visible and "catalog_items_list" in visible
            assert "catalog_items_create" in visible
            assert "settings_module_activation_preview" not in visible
            assert "crm_contacts_list" not in visible
        assert directory_calls == [str(ACTOR)]

        legacy_campaign = rpc(
            on_behalf_of, "tools/call", {"name": "crm_campaigns_list", "arguments": {}}
        )
        assert legacy_campaign["result"]["structuredContent"]["code"] == "forbidden"

        listed_skills = rpc(direct, "skills/list", {})["result"]["skills"]
        assert len(listed_skills) == 25
        legacy_skills = (
            "crm-campaigns",
            "crm-core",
            "crm-deals",
            "solution-selling/crm-discovery",
            "solution-selling/crm-prompters",
            "solution-selling/crm-prospecting",
            "solution-selling/solution-selling-workflow",
        )
        listed_uris = {skill["uri"] for skill in listed_skills}
        for skill in legacy_skills:
            uri = f"skill://{skill}/SKILL.md"
            assert uri not in listed_uris
            entry = rpc(direct, "skills/get", {"uri": uri})["result"]["skill"]
            assert entry["uri"] == uri
            for resource in entry["resources"]:
                read = rpc(direct, "resources/read", {"uri": resource["uri"]})
                content = read["result"]["contents"][0]
                assert (
                    resource["digest"]
                    == "sha256:" + hashlib.sha256(content["text"].encode()).hexdigest()
                )

        capabilities_for_actor.remove("catalog.write")
        create_item = {
            "name": "catalog_items_create",
            "arguments": {
                "name": "Denied write",
                "code": "DENIED",
                "kind": "service",
                "unit_uid": str(ACTOR),
                "category_uid": str(ACTOR),
            },
        }
        result = rpc(on_behalf_of, "tools/call", create_item)
        assert result["result"]["structuredContent"]["code"] == "forbidden"
        lookup = rpc(
            on_behalf_of,
            "tools/call",
            {
                "name": "erp_tools_describe",
                "arguments": {"module": "catalog", "name": "catalog_items_create"},
            },
        )
        assert lookup["result"]["structuredContent"]["data"]["tools"] == []
        capabilities_for_actor.remove("catalog.read")
        catalog_call = {"name": "catalog_items_list", "arguments": {}}
        denial = rpc(on_behalf_of, "tools/call", catalog_call)
        assert denial["result"]["structuredContent"]["code"] == "forbidden"
        active.clear()
        denial = rpc(on_behalf_of, "tools/call", catalog_call)
        assert denial["result"]["structuredContent"]["code"] == "module_disabled"

        workload = signed_caller(AGENT, is_organization_admin=True)
        denial = rpc(workload, "tools/call", {"name": "erp_modules_list", "arguments": {}})
        assert denial["result"]["structuredContent"]["code"] == "forbidden"
        assert "error" in rpc(workload, "tools/list", {})
        blocked_origin = client.post(
            "/mcp",
            headers={**MCP_HEADERS, **on_behalf_of, "Origin": "https://invalid.example"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        assert blocked_origin.status_code == 403
