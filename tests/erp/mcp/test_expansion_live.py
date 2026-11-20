"""Exercise the ERP agent boundary with synthetic records in disposable SQLite."""

import os
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import pytest

from metatables import configure_local_client, get_runtime_status

HEADERS = {
    "Accept": "application/json, text/event-stream",
    "MCP-Protocol-Version": "2025-11-25",
}


def rpc(client, method, **params):
    return (
        client.post(
            "/mcp",
            headers=HEADERS,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        )
        .raise_for_status()
        .json()["result"]
    )


@pytest.fixture
def erp():
    origin = os.getenv("ERP_MCP_EXPANSION_ORIGIN")
    if not origin:
        pytest.skip("Set ERP_MCP_EXPANSION_ORIGIN for a disposable all-module local runtime.")
    parsed = urlsplit(origin)
    assert parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port
    assert not (
        parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password
    )
    configure_local_client()
    state = get_runtime_status()
    assert state["local_mode"] and state["dialect"] == "sqlite"
    assert state["bootstrap"]["active"] and state["bootstrap"]["status"] == "ready"
    assert state["data_source"]["uid"] == os.environ["ERP_USER_PREFERENCES_DATA_SOURCE_UID"]
    assert (
        Path(state["bootstrap"]["candidate"]["configuration"]["path"]).resolve()
        == Path(os.environ["ERP_MCP_TEST_SQLITE"]).resolve()
    )
    with httpx.Client(base_url=origin, timeout=60, trust_env=False) as client:
        boot = client.get("/api/erp/v1/bootstrap/").raise_for_status().json()
        assert boot["organization_environment_uid"] == os.environ["ERP_MCP_EXPANSION_SCOPE"]
        assert len([x for x in boot["modules"] if x["can_access"]]) == 14
        yield client


def call(client, tool, *, expect="ok", **arguments):
    result = rpc(client, "tools/call", name=tool, arguments=arguments)
    body = result["structuredContent"]
    assert body["code"] == expect, (tool, body)
    assert result["isError"] == (expect != "ok")
    return body.get("data")


def request():
    return str(uuid4())


def transition(client, tool, record, **changes):
    return call(client, tool, uid=record["uid"], expected_version=record["version"], **changes)


def audit_actions(client, path, **params):
    events = client.get(path, params=params).raise_for_status().json()["items"]
    return {event["action"] for event in events}


def business(client):
    tag = "MCP-" + uuid4().hex[:8].upper()
    customer = call(client, "base_parties_create", name=tag + " Customer", kind="organization")
    currency = next(
        x
        for x in call(client, "settings_currencies_list", search="EUR")["items"]
        if x["code"] == "EUR"
    )
    company = call(
        client,
        "settings_operating_companies_create",
        name=tag,
        party_uid=customer["uid"],
        currency_uid=currency["uid"],
    )
    return (
        tag,
        customer["uid"],
        {
            "operating_company_uid": company["uid"],
            "currency_uid": currency["uid"],
        },
    )


def test_agent_commercial_purchase_and_manufacturing_workflows(erp):
    tag, party, company = business(erp)
    setup = call(erp, "erp_tools_describe", module="sales", name="sales_orders_create")
    assert [tool["name"] for tool in setup["tools"]] == ["sales_orders_create"]
    assert setup["tools"][0]["input_schema"]["additionalProperties"] is False
    group = call(erp, "catalog_unit_groups_create", name=tag, code=tag)
    unit = call(
        erp,
        "catalog_units_create",
        name=tag,
        code=tag,
        group_uid=group["uid"],
        is_reference=True,
        rounding_increment="1",
    )
    category = call(erp, "catalog_categories_create", name=tag, code=tag)
    component, output = (
        call(
            erp,
            "catalog_items_create",
            name=tag + suffix,
            code=tag + suffix,
            kind="product",
            unit_uid=unit["uid"],
            category_uid=category["uid"],
        )
        for suffix in ("-RAW", "-FINISHED")
    )
    prices = [{"item_uid": component["uid"], "quantity": "6", "unit_price": "12.50"}]
    order = call(
        erp,
        "sales_orders_create",
        request_uid=request(),
        name=tag,
        customer_uid=party,
        lines=prices,
        **company,
    )
    order = transition(erp, "sales_orders_quote", order)
    order = transition(erp, "sales_orders_confirm", order)
    dates = {"document_date": "2026-11-19", "due_date": "2026-12-19"}
    invoice_args = dict(request_uid=request(), order_uid=order["uid"], name=tag, **dates)
    call(
        erp,
        "finance_invoices_create_from_sales",
        expect="conflict",
        expected_order_version=order["version"] - 1,
        **invoice_args,
    )
    invoice = call(
        erp,
        "finance_invoices_create_from_sales",
        expected_order_version=order["version"],
        **invoice_args,
    )
    assert invoice["source_order_uid"] == order["uid"]
    assert Decimal(invoice["total"]) == Decimal("75.00") and invoice["state"] == "draft"
    assert call(erp, "finance_invoices_get", uid=invoice["uid"]) == invoice
    assert (
        call(erp, "finance_allocations_list", resource="invoices", uid=invoice["uid"])["items"]
        == []
    )
    assert "confirm" in audit_actions(erp, "/api/sales/v1/audit/", record_uid=order["uid"])
    assert "from-sales" in audit_actions(
        erp,
        "/api/finance/v1/audit/",
        resource="invoices",
        record_uid=invoice["uid"],
    )

    source, stock, destination, production = (
        call(
            erp,
            "inventory_locations_create",
            request_uid=request(),
            name=tag + suffix,
            code=tag + suffix,
            usage=usage,
            operating_company_uid=company["operating_company_uid"],
        )
        for suffix, usage in (
            ("-SUP", "supplier"),
            ("-STORE", "internal"),
            ("-PACK", "internal"),
            ("-PROD", "production"),
        )
    )
    raw_policy, final_policy = (
        call(
            erp,
            "inventory_stock_items_create",
            request_uid=request(),
            item_uid=item["uid"],
            unit_cost=cost,
            operating_company_uid=company["operating_company_uid"],
        )
        for item, cost in ((component, "5.00"), (output, "10.00"))
    )

    purchase = call(
        erp,
        "purchasing_orders_create",
        request_uid=request(),
        name=tag + "-PO",
        supplier_uid=party,
        lines=prices,
        **company,
    )
    purchase = transition(erp, "purchasing_orders_confirm", purchase)
    bill_args = dict(request_uid=request(), name=tag + "-BILL", **dates)
    call(
        erp,
        "purchasing_orders_create_vendor_bill",
        expect="conflict",
        uid=purchase["uid"],
        expected_version=purchase["version"],
        **bill_args,
    )
    purchase = transition(
        erp,
        "purchasing_order_lines_receive_stock",
        purchase,
        line_uid=purchase["lines"][0]["uid"],
        name=tag,
        request_uid=request(),
        stock_item_uid=raw_policy["uid"],
        source_uid=source["uid"],
        destination_uid=stock["uid"],
    )
    movement = call(erp, "inventory_movements_get", uid=purchase["receipts"][0]["movement_uid"])
    assert movement["snapshot"]["purchase_order_uid"] == purchase["uid"]
    movement = transition(erp, "inventory_movements_prepare", movement)
    transition(erp, "inventory_movements_complete", movement)
    purchase = transition(erp, "purchasing_orders_close", purchase)
    purchase = transition(erp, "purchasing_orders_create_vendor_bill", purchase, **bill_args)
    bill = call(erp, "finance_invoices_get", uid=purchase["bill_uid"])
    assert bill["kind"] == "vendor" and bill["source_purchase_order_uid"] == purchase["uid"]
    assert "close" in audit_actions(erp, "/api/purchasing/v1/audit/", record_uid=purchase["uid"])

    bom = call(
        erp,
        "manufacturing_boms_create",
        request_uid=request(),
        name=tag,
        item_uid=output["uid"],
        quantity="1",
        components=[{"item_uid": component["uid"], "quantity": "2"}],
        operations=["Assemble"],
    )
    bom = transition(erp, "manufacturing_boms_activate", bom)
    batch = call(
        erp,
        "manufacturing_orders_create",
        request_uid=request(),
        name=tag,
        bom_uid=bom["uid"],
        expected_bom_version=bom["version"],
        quantity="2",
        operating_company_uid=company["operating_company_uid"],
        source_uid=stock["uid"],
        destination_uid=destination["uid"],
        production_location_uid=production["uid"],
    )
    call(
        erp,
        "manufacturing_orders_complete",
        expect="conflict",
        uid=batch["uid"],
        expected_version=batch["version"],
    )
    batch = transition(erp, "manufacturing_orders_reserve", batch)
    assert len(batch["movement_uids"]) == 2
    step = batch["steps"][0]
    batch = transition(
        erp,
        "manufacturing_steps_start",
        batch,
        step_uid=step["uid"],
        expected_step_version=step["version"],
    )
    step = batch["steps"][0]
    batch = transition(
        erp,
        "manufacturing_steps_finish",
        batch,
        step_uid=step["uid"],
        expected_step_version=step["version"],
        minutes=5,
        evidence="Local test",
    )
    batch = transition(erp, "manufacturing_orders_complete", batch)
    assert batch["state"] == "done"
    ledger_url = f"/api/manufacturing/v1/orders/{batch['uid']}/finance/"
    erp.post(ledger_url, json={"expected_version": batch["version"]}).raise_for_status()
    valuation = call(erp, "manufacturing_orders_valuation", uid=batch["uid"])
    assert len(valuation["items"]) == 2
    assert sum(Decimal(row["net_value"]) for row in valuation["items"]) == 0
    for row in valuation["items"]:
        assert row["finance_posted"] and len(row["entries"]) == 2
        assert sum(Decimal(entry["amount"]) for entry in row["entries"]) == 0
    assert {"reserve", "work_finish", "complete", "finance"} <= audit_actions(
        erp,
        f"/api/manufacturing/v1/orders/{batch['uid']}/audit/",
    )
    assert final_policy["item_uid"] == output["uid"]


def test_agent_module_boundaries_and_local_reporting(erp):
    tag, party, company = business(erp)
    names = {tool["name"] for tool in rpc(erp, "tools/list")["tools"]}
    assert {
        "base_parties_archive",
        "catalog_items_archive",
        "finance_invoices_post",
        "finance_allocations_reverse",
        "inventory_movements_reverse",
        "manufacturing_orders_finance",
        "commerce_sites_publish",
        "commerce_grants_create",
        "settings_module_activation_commit",
        "finance_bank_reconciliation_commit",
    }.isdisjoint(names)
    project = call(
        erp,
        "projects_projects_create",
        request_uid=request(),
        name=tag,
        customer_uid=party,
        operating_company_uid=company["operating_company_uid"],
    )
    task = call(
        erp,
        "projects_tasks_create",
        request_uid=request(),
        name=tag,
        project_uid=project["uid"],
        expected_project_version=project["version"],
    )
    assert call(erp, "projects_tasks_get", uid=task["uid"])["project_uid"] == project["uid"]
    department = call(
        erp,
        "people_departments_create",
        request_uid=request(),
        name=tag,
        operating_company_uid=company["operating_company_uid"],
    )
    email = f"{tag.lower()}@example.com"
    person = call(erp, "base_parties_create", name=tag + " Person", kind="person", emails=[email])
    employee = call(
        erp,
        "people_employees_create",
        request_uid=request(),
        person_uid=person["uid"],
        department_uid=department["uid"],
        operating_company_uid=company["operating_company_uid"],
        start_date="2026-11-19",
    )
    assert call(erp, "people_employees_get", uid=employee["uid"])["person_uid"] == person["uid"]
    discussion = call(
        erp,
        "collaboration_discussions_create",
        request_uid=request(),
        name=tag,
        scope="project",
        project_uid=project["uid"],
        audience="authorized_project_readers",
    )
    posted = call(
        erp,
        "collaboration_messages_post",
        uid=discussion["uid"],
        request_uid=request(),
        expected_discussion_version=discussion["version"],
        body="Synthetic fixture",
    )
    assert (
        call(erp, "collaboration_messages_get", uid=posted["message"]["uid"])["body"]
        == "Synthetic fixture"
    )
    mailing = call(
        erp,
        "marketing_mailings_create",
        request_uid=request(),
        name=tag,
        subject=tag,
        body="Synthetic fixture",
        sender_email="fixture@example.com",
    )
    assert call(erp, "marketing_mailings_get", uid=mailing["uid"])["state"] == "draft"
    subscriber = call(
        erp,
        "marketing_subscribers_create",
        request_uid=request(),
        party_uid=person["uid"],
        email=email,
        evidence="Synthetic SQLite fixture",
    )
    attached = transition(
        erp,
        "marketing_recipients_add",
        mailing,
        subscriber_uid=subscriber["uid"],
        request_uid=request(),
    )
    mailing = transition(
        erp,
        "marketing_mailings_queue",
        attached["mailing"],
        acknowledge_local_capture=True,
    )
    mailing = transition(erp, "marketing_mailings_capture", mailing)
    assert mailing["state"] == "completed"
    recipient = call(erp, "marketing_recipients_get", uid=attached["recipient"]["uid"])
    assert recipient["state"] == "captured"
    recipient = transition(
        erp,
        "marketing_recipients_simulate",
        recipient,
        expected_mailing_version=mailing["version"],
        kind="opened",
        evidence="Synthetic engagement",
    )
    events = call(erp, "marketing_recipients_events", uid=recipient["uid"])["items"]
    assert any(event["kind"] == "opened" and event["mode"] == "simulated" for event in events)

    site = call(
        erp, "commerce_sites_create", request_uid=request(), name=tag, slug=tag.lower(), **company
    )
    assert call(erp, "commerce_sites_get", uid=site["uid"])["state"] == "draft"
    policy = call(erp, "settings_module_activation_get")
    assert policy["policy_version"] >= 1
    call(
        erp,
        "settings_module_activation_preview",
        expected_version=policy["policy_version"],
        active_module_keys=policy["active_module_keys"],
    )
    assert call(erp, "settings_module_activation_get") == policy
    preferences = call(erp, "settings_preferences_get")
    saved = call(
        erp,
        "settings_preferences_update",
        expected_version=preferences["version"],
        hidden_module_keys=preferences["hidden_module_keys"],
    )
    assert saved["version"] == preferences["version"] + 1
    locale = call(erp, "settings_locale_preferences_get")["preference"]
    language = next(
        row
        for row in call(erp, "settings_languages_list", search="en")["items"]
        if row["code"] == "en"
    )
    locale = call(
        erp,
        "settings_locale_preferences_update",
        expected_version=locale["version"] if locale else 0,
        language_uid=language["uid"],
        timezone="UTC",
    )["preference"]
    updated = call(
        erp,
        "settings_locale_preferences_update",
        expected_version=locale["version"],
        timezone="Europe/Vienna",
    )["preference"]
    assert updated["language_uid"] == language["uid"] and updated["timezone"] == "Europe/Vienna"
    definition = call(
        erp,
        "reporting_definitions_create",
        request_uid=request(),
        name=tag,
        kind="commercial",
        search=tag,
    )
    run = call(
        erp,
        "reporting_runs_start",
        request_uid=request(),
        definition_uid=definition["uid"],
        expected_definition_version=definition["version"],
    )
    for _ in range(8):
        if run["state"] == "succeeded":
            break
        run = transition(erp, "reporting_runs_advance", run)
    assert run["state"] == "succeeded", run
    call(erp, "reporting_runs_result", uid=run["uid"])
    call(erp, "reporting_runs_verify", uid=run["uid"])
    erp.post("/api/reporting/v1/worker/tick/", json={}).raise_for_status()
    assert erp.get("/api/reporting/v1/worker/status/").raise_for_status().json()["available"]
    schedule = call(
        erp,
        "reporting_schedules_create",
        request_uid=request(),
        name=tag,
        definition_uid=definition["uid"],
        interval_minutes=60,
    )
    schedule = transition(erp, "reporting_schedules_activate", schedule)
    schedule = transition(erp, "reporting_schedules_pause", schedule)
    assert schedule["state"] == "paused"
