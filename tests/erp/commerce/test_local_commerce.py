from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select, update

from src.erp.commerce.errors import CommerceError
from src.erp.commerce.metatables import Checkout, PortalGrant
from src.erp.commerce.schemas import CheckoutCreate, SiteInput
from src.erp.commerce.service import now


def error(code, call):
    with pytest.raises(CommerceError) as e:
        call()
    assert e.value.status == code, e.value.message


def test_public_checkout_invoice_recorded_payment_and_replay(commerce):
    f = commerce
    s = f["commerce"]
    token = f["access"]["token"]
    public = s.public_site(f["site"]["slug"])
    assert "operating_company_uid" not in public and "snapshot" not in public["offers"][0]
    row, payload = f["checkout"](token, f["site"], f["offer"])
    assert row["net_total"] == "25.00" and row["payment"]["status"] == "not_invoiced"
    assert s.checkout(token, payload)["uid"] == row["uid"]
    error(
        409,
        lambda: s.checkout(token, {**payload, "lines": [{**payload["lines"][0], "quantity": "3"}]}),
    )
    private = s.get("checkouts", row["uid"])
    order = f["sales"].get(private["sales_order_uid"])
    assert order["state"] == "confirmed" and order["downstream"] == {f"commerce:{row['uid']}": True}
    private = f["invoice"](private, tax_rate="20")
    assert s.portal_checkout(token, row["uid"])["payment"]["status"] == "draft"
    allocation = f["pay"](private)
    outcome = s.portal_checkout(token, row["uid"])["payment"]
    assert outcome["status"] == "paid" and Decimal(outcome["allocated"]) == 30
    f["finance"].reverse_allocation(
        allocation["allocation_uid"],
        allocation["invoice"]["version"],
        allocation["payment"]["version"],
    )
    assert s.portal_checkout(token, row["uid"])["payment"]["status"] == "unpaid"
    error(409, lambda: f["invoice"](private))


def test_token_scope_expiry_revocation_and_no_secret_reads(commerce):
    f = commerce
    s = f["commerce"]
    access = f["access"]
    token = access["token"]
    row, _ = f["checkout"](token, f["site"], f["offer"])
    other = f["grant"](f["site"])
    error(404, lambda: s.portal_checkout(other["token"], row["uid"]))
    assert s.portal_orders(other["token"])["items"] == []
    for bad in [
        "",
        token + "x",
        str(uuid4()) + "." + "a" * 43,
        token.split(".")[0] + "." + "a" * 43,
    ]:
        error(403, lambda: s.portal_orders(bad))
    assert "secret_digest" not in s.get("grants", access["grant"]["uid"])
    assert all("secret_digest" not in r for r in s.collection("grants")["items"])
    stored = s.raw("grants", access["grant"]["uid"])
    assert token not in str(stored) and token.split(".")[1] not in str(stored)
    s.revoke(access["grant"]["uid"], s.get("grants", access["grant"]["uid"])["version"])
    error(403, lambda: s.portal_checkout(token, row["uid"]))
    s.store.write(
        [
            update(PortalGrant)
            .where(PortalGrant.uid == UUID(other["grant"]["uid"]))
            .values(expires_at=now() - timedelta(seconds=1))
        ]
    )
    error(403, lambda: s.portal_orders(other["token"]))


def test_visibility_strict_input_and_stale_publication(commerce):
    f = commerce
    s = f["commerce"]
    site = f["site"]
    offer = f["offer"]
    token = f["access"]["token"]
    with pytest.raises(ValidationError):
        CheckoutCreate(
            request_uid=uuid4(),
            expected_site_version=site["version"],
            lines=[
                {
                    "offer_uid": offer["uid"],
                    "expected_version": offer["version"],
                    "quantity": "2",
                    "unit_price": "0",
                }
            ],
        )
    error(
        422,
        lambda: f["checkout"](
            token,
            site,
            offer,
            lines=[
                {
                    "offer_uid": offer["uid"],
                    "expected_version": offer["version"],
                    "quantity": "0.001",
                }
            ],
        ),
    )
    error(
        409,
        lambda: s.save(
            "sites",
            {k: site[k] for k in SiteInput.model_fields},
            uid=site["uid"],
            expected_version=site["version"],
        ),
    )
    offer = s.publish("offers", offer["uid"], "unpublish", offer["version"])
    assert s.public_site(site["slug"])["offers"] == []
    error(409, lambda: f["checkout"](token, site, f["offer"]))
    s.publish("sites", site["uid"], "unpublish", site["version"])
    error(404, lambda: s.public_site(site["slug"]))
    error(409, lambda: f["grant"](site))


def test_checkout_race_and_late_grant_revoke_roll_back_sales(commerce, monkeypatch):
    f = commerce
    s = f["commerce"]
    token = f["access"]["token"]
    site = f["site"]
    offer = f["offer"]
    uid = uuid4()
    f["commerce_owned"]["checkouts"].append(uid)
    payload = {
        "request_uid": uid,
        "expected_site_version": site["version"],
        "lines": [
            {"offer_uid": offer["uid"], "expected_version": offer["version"], "quantity": "2"}
        ],
    }
    barrier = Barrier(2)

    def run(_):
        barrier.wait()
        try:
            return s.checkout(token, payload)
        except CommerceError as e:
            return e.status

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(run, range(2)))
    assert any(isinstance(x, dict) for x in results)
    assert len(s.store.read(select(Checkout.uid).where(Checkout.uid == uid))) == 1
    assert s.checkout(token, payload)["uid"] == str(uid)
    original = f["sales"].plan_commerce_checkout

    def revoke(*args, **kwargs):
        order, plan = original(*args, **kwargs)
        grant = s.get("grants", f["access"]["grant"]["uid"])
        s.revoke(grant["uid"], grant["version"])
        return order, plan

    monkeypatch.setattr(f["sales"], "plan_commerce_checkout", revoke)
    error(409, lambda: f["checkout"](token, site, offer))
    assert s.collection("checkouts", search="WEB-" + uid.hex.upper())["pageInfo"]["totalItems"] == 1


def test_optional_owners_permissions_source_and_late_invoice_rollback(commerce, monkeypatch):
    import src.erp.commerce.store as store_module
    from src.erp.commerce.dependencies import OwnerPort
    from src.erp.commerce.service import Service
    from src.erp.finance.metatables import Invoice
    from src.erp.sales.service import Service as SalesService

    f = commerce
    s = f["commerce"]
    token = f["access"]["token"]
    sales = f["sales"]
    denied = Service(s.store, s.actor_uid, {"commerce.read"}, s.dependencies)
    error(
        403,
        lambda: denied.issue_grant(
            {
                "request_uid": uuid4(),
                "site_uid": f["site"]["uid"],
                "customer_uid": f["payload"]["customer_uid"],
            }
        ),
    )
    with monkeypatch.context() as p:
        p.setattr(s.dependencies, "sales_factory", None)
        assert not s.public_site(f["site"]["slug"])["checkout_enabled"]
        error(503, lambda: f["checkout"](token, f["site"], f["offer"]))
    with monkeypatch.context() as p:
        p.setattr(
            s.dependencies,
            "sales_factory",
            lambda: OwnerPort(
                SalesService(sales.store, sales.actor_uid, {"sales.read"}, sales.dependencies)
            ),
        )
        error(403, lambda: f["checkout"](token, f["site"], f["offer"]))
    row, _ = f["checkout"](token, f["site"], f["offer"])
    private = s.get("checkouts", row["uid"])
    with monkeypatch.context() as p:
        p.setattr(s.dependencies, "finance_factory", None)
        error(503, lambda: f["invoice"](private))
    original = f["finance"].plan_from_sales

    def conflict(payload):
        uid, plan = original(payload)
        s.store.write(
            [
                update(Checkout)
                .where(Checkout.uid == UUID(row["uid"]))
                .values(version=Checkout.version + 1)
            ]
        )
        return uid, plan

    with monkeypatch.context() as p:
        p.setattr(f["finance"], "plan_from_sales", conflict)
        error(409, lambda: f["invoice"](private))
    assert s.get("checkouts", row["uid"])["invoice_uid"] is None
    assert not f["finance"].store.read(
        select(Invoice.uid).where(Invoice.source_order_uid == UUID(private["sales_order_uid"]))
    )
    assert not any(
        x.startswith("finance:") for x in sales.get(private["sales_order_uid"])["downstream"]
    )
    fake = type("Other", (), {"store": type("Source", (), {"data_source_uid": str(uuid4())})()})()
    error(503, lambda: s.same_source(fake))
    with monkeypatch.context() as p:
        p.setattr(store_module, "require_local_runtime", lambda: str(uuid4()))
        with pytest.raises(RuntimeError):
            s.store.write([])


def test_actual_private_public_http_and_persistence(commerce):
    import json
    import subprocess
    from pathlib import Path

    from fastapi.testclient import TestClient
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    from api.erp.commerce.local import create_app
    from api.erp.commerce.public_local import create_app as public_app
    from metatables import upgrade_application
    from src.erp.commerce.metatables import MODELS

    f = commerce
    token = f["access"]["token"]
    s = f["commerce"]
    assert upgrade_application("src.erp.commerce.migrations:migration")["revision"] == "0001"
    assert {m.__metatable_namespace__ for m in MODELS} == {"erp-commerce"}
    code = """import sys
from metatables import configure_local_client
configure_local_client()
from src.erp.commerce.store import Store
from src.erp.commerce.metatables import Site
from api.erp.commerce.main import create_app
from sqlalchemy import select
from uuid import UUID
assert 'src.erp.sales.service' not in sys.modules and 'src.erp.finance.service' not in sys.modules
assert not any(r.path.startswith('/api/commerce') for r in create_app(enabled_module=False).routes)
print(Store(local_only=True).read(select(Site.uid).where(Site.uid==UUID(sys.argv[1])))[0]['uid'])
"""
    assert f["site"]["uid"] in subprocess.check_output(
        [".venv/bin/python", "-c", code, f["site"]["uid"]], text=True
    )
    schemas = [
        json.loads(p.read_text())
        for p in Path("tests/erp/commerce/contracts/sdk-0.5.19/schemas").glob("*.json")
    ]
    registry = Registry().with_resources([(x["$id"], Resource.from_contents(x)) for x in schemas])
    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 50000)
    ) as client:
        assert client.get("/api/commerce/v1/ready/").status_code == 200
        for resource in ["sites", "offers", "grants", "checkouts"]:
            for suffix, name in [("", "resource-collection"), ("discovery/", "resource-discovery")]:
                response = client.get(f"/api/commerce/v1/{resource}/{suffix}")
                assert response.status_code == 200, response.text
                Draft202012Validator(
                    next(x for x in schemas if name in x["$id"]), registry=registry
                ).validate(response.json())
        for headers in [
            {"x-user-uid": str(uuid4())},
            {"Origin": "https://external.example"},
            {"Host": "external.example"},
        ]:
            assert client.get("/api/commerce/v1/ready/", headers=headers).status_code in (401, 403)
        # Explicit action routes must win over the generic publication route.
        extra = f["grant"](f["site"])["grant"]
        response = client.post(
            f"/api/commerce/v1/grants/{extra['uid']}/revoke/",
            json={"expected_version": extra["version"]},
        )
        assert response.status_code == 200, response.text
    with TestClient(
        public_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 50000)
    ) as client:
        url = f"/api/commerce-public/v1/sites/{f['site']['slug']}/"
        response = client.get(url)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert client.get("/api/commerce/v1/sites/").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        for headers in [
            {"Authorization": "Bearer fake"},
            {"x-user-uid": str(uuid4())},
            {"Origin": "https://external.example"},
            {"Host": "external.example"},
        ]:
            assert client.get(url, headers=headers).status_code == 403
        assert client.get("/api/commerce-public/v1/checkouts/").status_code == 403
        assert (
            client.get(
                "/api/commerce-public/v1/checkouts/?token=ignored",
                headers={"x-portal-token": token},
            ).status_code
            == 422
        )
        uid = uuid4()
        f["commerce_owned"]["checkouts"].append(uid)
        payload = {
            "request_uid": str(uid),
            "expected_site_version": f["site"]["version"],
            "lines": [
                {
                    "offer_uid": f["offer"]["uid"],
                    "expected_version": f["offer"]["version"],
                    "quantity": "1",
                }
            ],
        }
        response = client.post(
            "/api/commerce-public/v1/checkouts/", json=payload, headers={"x-portal-token": token}
        )
        assert response.status_code == 201, response.text
        result = response.json()
        assert (
            not {"snapshot", "customer_uid", "sales_order_uid", "invoice_uid", "grant_uid"}
            & result.keys()
        )
        assert result["net_total"] == "12.50"
        assert (
            client.get(
                "/api/commerce-public/v1/checkouts/" + str(uid) + "/",
                headers={"x-portal-token": token},
            ).status_code
            == 200
        )
        assert "secret_digest" not in str(s.history("grants", f["access"]["grant"]["uid"]))


def test_maximum_checkout_exact_amount_and_service_only(commerce, monkeypatch):
    f = commerce
    s = f["commerce"]
    physical = f["product"]("product")
    error(422, lambda: f["create_offer"](f["site"], item_uid=physical["uid"]))
    offers = [f["offer"]]
    for _ in range(19):
        offers.append(f["create_offer"](f["site"], item_uid=f["product"]()["uid"]))
    counts = []
    original = s.store.write

    def write(steps):
        counts.append(len(steps))
        return original(steps)

    monkeypatch.setattr(s.store, "write", write)
    row, _ = f["checkout"](
        f["access"]["token"],
        f["site"],
        offers[0],
        lines=[
            {"offer_uid": offer["uid"], "expected_version": offer["version"], "quantity": "1"}
            for offer in offers
        ],
    )
    assert row["net_total"] == "250.00" and len(row["lines"]) == 20 and max(counts) <= 32
    assert s.public_site(f["site"]["slug"], page_size=7)["pageInfo"]["hasNextPage"]
