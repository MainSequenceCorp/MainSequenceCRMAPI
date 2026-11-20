"""Opt-in loopback verification of the MCP pilot through real SDK identity and SQLite."""

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import anyio
import httpx
import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from api.erp.mcp.registry import SKILLS_ROOT
from metatables import configure_local_client, get_runtime_status

TOOL_NAMES = {"erp_modules_list", "catalog_units_convert"} | {
    f"{owner}_{resource}_{operation}"
    for owner, resources in (
        ("base", ("parties", "affiliations", "addresses")),
        ("catalog", ("items", "categories", "units", "unit_groups")),
    )
    for resource in resources
    for operation in ("list", "get")
}
PILOT_SKILLS = ("erp/erp-workflows", "base/base-directory", "catalog/catalog-items")


def _fixtures(client, marker):
    base, catalog = "/api/base/v1", "/api/catalog/v1"

    def create(prefix, resource, **payload):
        response = client.post(f"{prefix}/{resource}/", json=payload)
        assert response.status_code == 201, (resource, response.text)
        return response.json()

    party = create(base, "parties", name=f"{marker} Person", kind="person")
    org = create(base, "parties", name=f"{marker} Company", kind="organization")
    affiliation = create(
        base,
        "affiliations",
        name=f"{marker} Affiliation",
        person_uid=party["uid"],
        organization_uid=org["uid"],
        role="Reviewer",
    )
    countries = client.get(f"{base}/countries/").raise_for_status().json()["items"]
    address = create(
        base,
        "addresses",
        name=f"{marker} Address",
        party_uid=party["uid"],
        country_uid=countries[0]["uid"],
        street="1 Test Lane",
        city="Test City",
    )
    category = create(catalog, "categories", name=f"{marker} Category", code=f"{marker}-CAT")
    group = create(catalog, "unit-groups", name=f"{marker} Group", code=f"{marker}-GROUP")
    reference = create(
        catalog,
        "units",
        name=f"{marker} Unit",
        code=f"{marker}-UNIT",
        group_uid=group["uid"],
        is_reference=True,
        rounding_increment="1",
    )
    dozen = create(
        catalog,
        "units",
        name=f"{marker} Dozen",
        code=f"{marker}-DOZEN",
        group_uid=group["uid"],
        factor="12",
        rounding_increment="1",
    )
    item = create(
        catalog,
        "items",
        name=f"{marker} Item",
        code=f"{marker}-ITEM",
        kind="service",
        unit_uid=reference["uid"],
        category_uid=category["uid"],
    )
    cases = [
        (base, "parties", party, {"kind": "person"}),
        (base, "affiliations", affiliation, {}),
        (base, "addresses", address, {}),
        (catalog, "items", item, {"kind": "service"}),
        (catalog, "categories", category, {}),
        (catalog, "unit-groups", group, {}),
        (catalog, "units", reference, {"group_uid": group["uid"]}),
    ]
    return cases, {"quantity": "2", "from_unit_uid": dozen["uid"], "to_unit_uid": reference["uid"]}


def test_every_pilot_tool_matches_rest_with_crm_disabled():
    origin = os.getenv("ERP_MCP_TEST_ORIGIN")
    if not origin:
        pytest.skip("Set ERP_MCP_TEST_ORIGIN and bind an isolated local SQLite pilot.")
    parsed = urlsplit(origin)
    assert parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port
    assert not (
        parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password
    )
    expected_sqlite = Path(os.environ["ERP_MCP_TEST_SQLITE"]).resolve()
    configure_local_client()
    state = get_runtime_status()
    assert state["local_mode"] is True and state["dialect"] == "sqlite"
    assert state["bootstrap"]["active"] and state["bootstrap"]["status"] == "ready"
    assert not state.get("data_source_error")
    assert (
        Path(state["bootstrap"]["candidate"]["configuration"]["path"]).resolve() == expected_sqlite
    )
    assert state["data_source"]["uid"] == os.environ["ERP_USER_PREFERENCES_DATA_SOURCE_UID"]

    with httpx.Client(base_url=origin, timeout=45, trust_env=False) as client:
        bootstrap = client.get("/api/erp/v1/bootstrap/").raise_for_status().json()
        assert bootstrap["organization_environment_uid"] == state["data_source"]["uid"]
        assert bootstrap["current_user"]["uid"]
        modules = {row["key"]: row for row in bootstrap["modules"]}
        assert modules["base"]["can_access"] and modules["catalog"]["can_access"]
        assert not modules["crm"]["active"]
        assert client.get("/api/crm/v1/settings/").status_code == 403
        marker = f"MCP-{uuid4().hex[:10].upper()}"
        fixtures, conversion = _fixtures(client, marker)
        cases = {"erp_modules_list": ({}, None)}
        for prefix, resource, record, filters in fixtures:
            owner = prefix.split("/")[2]
            stem = f"{owner}_{resource.replace('-', '_')}"
            query = {"search": marker, "page_size": 7, **filters}
            listed = client.get(f"{prefix}/{resource}/", params=query).raise_for_status().json()
            detail = client.get(f"{prefix}/{resource}/{record['uid']}/").raise_for_status().json()
            assert record["uid"] in {row["uid"] for row in listed["items"]}
            cases[f"{stem}_list"] = query, listed
            cases[f"{stem}_get"] = {"uid": record["uid"]}, detail
        converted = (
            client.post("/api/catalog/v1/convert/", json=conversion).raise_for_status().json()
        )
        assert converted["quantity"] == "24"
        cases["catalog_units_convert"] = conversion, converted
        assert set(cases) == TOOL_NAMES

    async def verify():
        async with httpx2.AsyncClient(timeout=60, trust_env=False) as client:
            async with streamable_http_client(origin + "/mcp", http_client=client) as (read, write):
                async with ClientSession(
                    read, write, extensions={"io.modelcontextprotocol/skills": {}}
                ) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    assert TOOL_NAMES <= {tool.name for tool in listed.tools}
                    assert not any(tool.name.startswith("crm_") for tool in listed.tools)
                    for name, (arguments, expected) in cases.items():
                        result = await session.call_tool(name, arguments)
                        assert not result.is_error, (name, result.structured_content)
                        body = result.structured_content
                        assert body["code"] == "ok"
                        assert json.loads(result.content[0].text) == body
                        if name == "erp_modules_list":
                            assert body["data"] == {
                                "modules": [
                                    {
                                        k: row[k]
                                        for k in (
                                            "key",
                                            "title",
                                            "provisioned",
                                            "active",
                                            "can_access",
                                            "prerequisites",
                                        )
                                    }
                                    for row in bootstrap["modules"]
                                ],
                                "policy_version": bootstrap["policy_version"],
                            }
                        else:
                            assert body["data"] == expected, name
                    deny = await session.call_tool("crm_contacts_list", {})
                    assert deny.is_error and deny.structured_content["code"] == "forbidden"
                    invalid = await session.call_tool("base_parties_list", {"page_size": "5"})
                    assert (
                        invalid.is_error
                        and invalid.structured_content["code"] == "invalid_arguments"
                    )
                    invalid = await session.call_tool(
                        "catalog_items_list", {"group_uid": str(uuid4())}
                    )
                    assert (
                        invalid.is_error
                        and invalid.structured_content["code"] == "invalid_arguments"
                    )
                    missing = await session.call_tool("base_parties_get", {"uid": str(uuid4())})
                    assert missing.is_error and missing.structured_content["code"] == "not_found"
                    for relative in (f"{path}/SKILL.md" for path in PILOT_SKILLS):
                        served = await session.read_resource("skill://" + relative)
                        actual = served.contents[0].text.encode()
                        expected = (SKILLS_ROOT / relative).read_bytes()
                        assert hashlib.sha256(actual).digest() == hashlib.sha256(expected).digest()
                    print("Real SDK MCP: all 16 pilot tools matched ERP REST with CRM disabled.")

    anyio.run(verify)
