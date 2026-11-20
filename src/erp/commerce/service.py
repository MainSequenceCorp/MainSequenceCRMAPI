"""Owned publication, scoped portal authority and atomic service checkouts."""

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from uuid import UUID, uuid4, uuid5

from sqlalchemy import func, insert, select, update

from mainsequence.client.exceptions import BadRequestError
from metatables import MetaTableTransactionGuardError
from metatables.compiled_sql.v1 import GuardedStatement
from src.erp.collections import read_page
from src.erp.module_access import module_available, require_module

from .errors import CommerceError
from .metatables import RESOURCES, AuditEvent, Checkout, Offer, PortalGrant, Site
from .schemas import CheckoutCreate, GrantCreate, InvoiceInput, OfferInput, SiteInput


def key(uid):
    return UUID(str(uid))


def now():
    return datetime.now(timezone.utc)


def timestamp(value):
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result


class Service:
    def __init__(self, store, actor_uid, capabilities, dependencies):
        self.store, self.actor_uid, self.capabilities, self.dependencies = (
            store,
            key(actor_uid),
            set(capabilities),
            dependencies,
        )

    def require(self, cap):
        require_module("commerce")
        if cap not in self.capabilities:
            raise CommerceError(403, "forbidden", "Commerce access does not permit this operation")

    def created(self):
        return dict(
            version=1,
            created_at=now(),
            updated_at=now(),
            created_by_uid=self.actor_uid,
            updated_by_uid=self.actor_uid,
        )

    def raw(self, resource, uid):
        model = RESOURCES.get(resource)
        if model is None:
            raise CommerceError(404, "not_found", "Unknown Commerce collection")
        rows = self.store.read(select(model.__table__).where(model.uid == key(uid)).limit(1))
        if not rows:
            raise CommerceError(404, "not_found", "Commerce record not found")
        return rows[0]

    def safe(self, row):
        return {k: v for k, v in row.items() if k not in {"secret_digest", "request_hash"}}

    def get(self, resource, uid):
        self.require("commerce.read")
        row = self.safe(self.raw(resource, uid))
        if resource in {"offers", "grants"}:
            site = self.raw("sites", row["site_uid"])
            row.update(site_name=site["name"], site_slug=site["slug"])
        return row

    def collection(self, resource, *, page_index=0, page_size=25, search="", state=None):
        self.require("commerce.read")
        model = RESOURCES.get(resource)
        if model is None:
            raise CommerceError(404, "not_found", "Unknown Commerce collection")
        terms = []
        if search:
            terms.append(func.lower(model.name).contains(search.lower(), autoescape=True))
        if state:
            terms.append(model.state == state)
        result = read_page(
            self.store,
            model.__table__,
            terms,
            (model.created_at.desc(), model.uid),
            page_index=page_index,
            page_size=page_size,
        )
        result["items"] = [self.safe(row) for row in result["items"]]
        return result

    def guard(self, model, row, expected, values=None, *, bump=True):
        if row["version"] != expected:
            raise CommerceError(409, "conflict", "Record changed; reload and review")
        changes = dict(values or {})
        changes.update(
            version=expected + 1, updated_at=now(), updated_by_uid=self.actor_uid
        ) if bump else changes.update(updated_at=model.updated_at)
        return GuardedStatement(
            update(model)
            .where(
                model.uid == key(row["uid"]), model.version == expected, model.state == row["state"]
            )
            .values(**changes)
            .returning(model.uid),
            expect_rows=1,
            label="commerce_version",
        )

    def audit(self, resource, uid, action, version, fields):
        return insert(AuditEvent).values(
            uid=uuid4(),
            resource=resource,
            record_uid=key(uid),
            actor_uid=self.actor_uid,
            action=action,
            version=version,
            occurred_at=now(),
            fields=sorted(k for k in fields if k not in {"secret_digest", "request_hash", "token"}),
        )

    def transact(self, steps):
        if len(steps) > 32:
            raise CommerceError(422, "batch_limit", "Checkout exceeds the atomic operation limit")
        try:
            return self.store.write(steps)
        except MetaTableTransactionGuardError as e:
            raise CommerceError(
                409, "conflict", "Access, offer or record changed; reload before retrying"
            ) from e
        except BadRequestError as e:
            detail = (getattr(e, "payload", {}) or {}).get("detail", {})
            if isinstance(detail, dict) and detail.get("code") == "compiled_sql_database_error":
                raise CommerceError(
                    409,
                    "constraint_conflict",
                    "Reference or request already exists; inspect the saved result",
                ) from e
            raise

    def same_source(self, owner):
        if str(owner.store.data_source_uid) != str(self.store.data_source_uid):
            raise CommerceError(
                503,
                "integration_source",
                "Commerce and its transaction owner must share the governed DataSource",
            )
        return owner

    def product(self, uid):
        item = self.dependencies.get("catalog", "items", uid)
        if item["kind"] != "service" or not item["saleable"]:
            raise CommerceError(
                422,
                "service_only",
                "Choose an active service available for sale; physical checkout is not supported",
            )
        unit = self.dependencies.get("catalog", "units", item["unit_uid"])
        self.dependencies.get("catalog", "unit-groups", unit["group_uid"])
        self.dependencies.get("catalog", "categories", item["category_uid"])
        return {
            "item_uid": item["uid"],
            "item_name": item["name"],
            "item_version": item["version"],
            "unit_uid": unit["uid"],
            "unit_name": unit["name"],
            "unit_version": unit["version"],
            "increment": unit["rounding_increment"],
        }

    def prepare(self, resource, payload):
        data = (SiteInput if resource == "sites" else OfferInput).model_validate(payload)
        values = data.model_dump()
        if resource == "sites":
            company = self.dependencies.get(
                "base", "operating-companies", data.operating_company_uid
            )
            currency = self.dependencies.get("base", "currencies", data.currency_uid)
            values["snapshot"] = {
                "company_name": company["name"],
                "currency_code": currency["code"],
                "minor_units": currency["minor_units"],
                "rounding": currency["rounding"],
            }
        else:
            self.raw("sites", data.site_uid)
            values["snapshot"] = self.product(data.item_uid)
        return values

    def save(self, resource, payload, *, request_uid=None, uid=None, expected_version=None):
        self.require("commerce.configure")
        if resource not in {"sites", "offers"}:
            raise CommerceError(404, "not_found", "This collection does not support editing")
        old = self.raw(resource, uid) if uid else None
        if old and old["state"] != "draft":
            raise CommerceError(409, "locked", "Unpublish before editing this record")
        values = self.prepare(resource, payload)
        immutable = (
            ["slug", "operating_company_uid", "currency_uid"]
            if resource == "sites"
            else ["site_uid", "item_uid"]
        )
        if old and any(str(old[k]) != str(values[k]) for k in immutable):
            raise CommerceError(
                422, "immutable", "Website identity, currency and source references cannot change"
            )
        target = key(uid or request_uid)
        model = RESOURCES[resource]
        plan = (
            [self.guard(model, old, expected_version, values)]
            if old
            else [insert(model).values(uid=target, state="draft", **values, **self.created())]
        )
        self.transact(
            [
                *plan,
                self.audit(
                    resource,
                    target,
                    "update" if old else "create",
                    expected_version + 1 if old else 1,
                    values,
                ),
            ]
        )
        return self.get(resource, target)

    def publish(self, resource, uid, action, expected):
        self.require("commerce.configure")
        row = self.raw(resource, uid)
        if (
            resource not in {"sites", "offers"}
            or action not in {"publish", "unpublish"}
            or row["state"] != ("draft" if action == "publish" else "published")
        ):
            raise CommerceError(409, "state", "Publication action is unavailable in this state")
        values = {"state": "published" if action == "publish" else "draft"}
        if action == "publish":
            fields = SiteInput.model_fields if resource == "sites" else OfferInput.model_fields
            values.update(self.prepare(resource, {k: row[k] for k in fields}))
        self.transact(
            [
                self.guard(RESOURCES[resource], row, expected, values),
                self.audit(resource, uid, action, expected + 1, values),
            ]
        )
        return self.get(resource, uid)

    def issue_grant(self, payload):
        self.require("commerce.manage")
        data = GrantCreate.model_validate(payload)
        site = self.raw("sites", data.site_uid)
        if site["state"] != "published":
            raise CommerceError(
                409, "site_hidden", "Publish the website before granting portal access"
            )
        party = self.dependencies.get("base", "parties", data.customer_uid)
        secret = secrets.token_urlsafe(32)
        values = dict(
            uid=data.request_uid,
            site_uid=data.site_uid,
            customer_uid=data.customer_uid,
            name=party["name"],
            state="active",
            secret_digest=hashlib.sha256(secret.encode()).hexdigest(),
            expires_at=now() + timedelta(minutes=30),
            **self.created(),
        )
        self.transact(
            [
                self.guard(Site, site, site["version"], bump=False),
                insert(PortalGrant).values(values),
                self.audit(
                    "grants",
                    data.request_uid,
                    "issue",
                    1,
                    ["site_uid", "customer_uid", "expires_at"],
                ),
            ]
        )
        return {
            "grant": self.get("grants", data.request_uid),
            "token": f"{data.request_uid}.{secret}",
        }

    def revoke(self, uid, expected):
        self.require("commerce.manage")
        row = self.raw("grants", uid)
        if row["state"] != "active":
            raise CommerceError(409, "state", "Grant is already revoked")
        self.transact(
            [
                self.guard(PortalGrant, row, expected, {"state": "revoked"}),
                self.audit("grants", uid, "revoke", expected + 1, ["state"]),
            ]
        )
        return self.get("grants", uid)

    def authorize(self, token):
        # No customer identity enters a platform identity context.
        denied = CommerceError(403, "portal_access", "Portal access is invalid, expired or revoked")
        if not isinstance(token, str) or len(token) > 128:
            raise denied
        try:
            uid, secret = token.split(".", 1)
            row = self.raw("grants", key(uid))
        except (ValueError, CommerceError):
            raise denied from None
        if (
            len(secret) != 43
            or not hmac.compare_digest(
                hashlib.sha256(secret.encode()).hexdigest(), row["secret_digest"]
            )
            or row["state"] != "active"
            or timestamp(row["expires_at"]) <= now()
        ):
            raise denied
        return row

    def public_site(self, slug, *, page_index=0, page_size=25):
        rows = self.store.read(
            select(Site.__table__).where(Site.slug == slug, Site.state == "published").limit(1)
        )
        if not rows:
            raise CommerceError(404, "not_found", "Published website not found")
        site = rows[0]
        terms = [Offer.site_uid == key(site["uid"]), Offer.state == "published"]
        total = int(
            self.store.read(select(func.count().label("count")).select_from(Offer).where(*terms))[
                0
            ]["count"]
        )
        rows = self.store.read(
            select(Offer.__table__)
            .where(*terms)
            .order_by(Offer.name, Offer.uid)
            .offset(page_index * page_size)
            .limit(page_size),
            max_rows=page_size,
        )
        return {
            "uid": site["uid"],
            "version": site["version"],
            "name": site["name"],
            "slug": site["slug"],
            "body": site["body"],
            "currency_code": site["snapshot"]["currency_code"],
            "checkout_enabled": module_available("sales") and self.dependencies.sales_factory is not None,
            "offers": [
                {
                    "uid": r["uid"],
                    "version": r["version"],
                    "name": r["name"],
                    "description": r["description"],
                    "unit_price": r["unit_price"],
                    "unit_name": r["snapshot"]["unit_name"],
                    "increment": r["snapshot"]["increment"],
                }
                for r in rows
            ],
            "pageInfo": {
                "pageIndex": page_index,
                "pageSize": page_size,
                "totalItems": total,
                "hasNextPage": (page_index + 1) * page_size < total,
                "hasPreviousPage": page_index > 0,
            },
        }

    def checkout(self, token, payload):
        grant = self.authorize(token)
        data = CheckoutCreate.model_validate(payload)
        digest = hashlib.sha256(
            json.dumps(
                data.model_dump(mode="json", exclude={"request_uid"}),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        existing = self.store.read(
            select(Checkout.__table__).where(Checkout.uid == data.request_uid).limit(1)
        )
        if existing:
            row = existing[0]
            if row["grant_uid"] != grant["uid"] or row["request_hash"] != digest:
                raise CommerceError(
                    409,
                    "request_conflict",
                    "This request identifier belongs to a different checkout attempt",
                )
            return self.portal_checkout(token, data.request_uid)
        site = self.raw("sites", grant["site_uid"])
        if site["state"] != "published" or site["version"] != data.expected_site_version:
            raise CommerceError(
                409, "site_changed", "Reload the current published website before checkout"
            )
        if len({x.offer_uid for x in data.lines}) != len(data.lines):
            raise CommerceError(422, "duplicate_offer", "Include each service offer only once")
        lines = []
        captures = []
        fences = []
        with localcontext() as ctx:
            ctx.prec = 100
            for line in data.lines:
                offer = self.raw("offers", line.offer_uid)
                if (
                    offer["site_uid"] != site["uid"]
                    or offer["state"] != "published"
                    or offer["version"] != line.expected_version
                ):
                    raise CommerceError(
                        409, "offer_changed", "Reload the published offer before checkout"
                    )
                product = self.product(offer["item_uid"])
                ticks = Decimal(line.quantity) / Decimal(product["increment"])
                if ticks != ticks.to_integral_value() or not 1 <= ticks <= 10**9:
                    raise CommerceError(
                        422,
                        "quantity_precision",
                        "Quantity must match the service unit increment and limit",
                    )
                if product["unit_uid"] != offer["snapshot"]["unit_uid"]:
                    raise CommerceError(
                        409,
                        "unit_changed",
                        "The service unit changed; ask the merchant to review the offer",
                    )
                lines.append(
                    {
                        "item_uid": offer["item_uid"],
                        "description": offer["name"],
                        "quantity": line.quantity,
                        "unit_price": offer["unit_price"],
                        "discount": "0",
                    }
                )
                captures.append(
                    {
                        "offer_uid": offer["uid"],
                        "offer_version": offer["version"],
                        "name": offer["name"],
                        "unit_name": product["unit_name"],
                        "quantity": line.quantity,
                        "unit_price": offer["unit_price"],
                    }
                )
                fences.append(self.guard(Offer, offer, line.expected_version, bump=False))
        sales = self.same_source(self.dependencies.sales())
        order_uid = uuid5(data.request_uid, "sales-order")
        name = "WEB-" + data.request_uid.hex.upper()
        order, plan = sales.plan_commerce_checkout(
            {
                "name": name,
                "customer_uid": grant["customer_uid"],
                "operating_company_uid": site["operating_company_uid"],
                "currency_uid": site["currency_uid"],
                "notes": "Service checkout; payment is recorded separately.",
                "lines": lines,
            },
            request_uid=order_uid,
            checkout_uid=data.request_uid,
        )
        if Decimal(order["net_total"]) <= 0:
            raise CommerceError(
                422, "zero_total", "Checkout net amount must be positive after currency rounding"
            )
        snapshot = {
            "site_name": site["name"],
            "site_slug": site["slug"],
            "customer_name": grant["name"],
            "currency_code": order["currency_code"],
            "company_name": order["company_name"],
            "lines": captures,
        }
        self.transact(
            [
                self.guard(PortalGrant, grant, grant["version"]),
                self.guard(Site, site, data.expected_site_version, bump=False),
                *fences,
                *plan,
                insert(Checkout).values(
                    uid=data.request_uid,
                    site_uid=key(site["uid"]),
                    grant_uid=key(grant["uid"]),
                    name=name,
                    state="placed",
                    sales_order_uid=order_uid,
                    invoice_uid=None,
                    request_hash=digest,
                    net_total=order["net_total"],
                    snapshot=snapshot,
                    **self.created(),
                ),
                self.audit(
                    "checkouts", data.request_uid, "checkout", 1, ["snapshot", "sales_order_uid"]
                ),
            ]
        )
        return self.portal_checkout(token, data.request_uid)

    def payment(self, row):
        if not row["invoice_uid"]:
            return {
                "status": "not_invoiced",
                "message": "No invoice yet; no payment processed by this website.",
            }
        try:
            finance = self.same_source(self.dependencies.finance())
            invoice = finance.get("invoices", row["invoice_uid"])
        except CommerceError as e:
            if e.status in {403, 503}:
                return {
                    "status": "unavailable",
                    "message": "Recorded payment status is temporarily unavailable.",
                }
            raise
        if invoice["source_order_uid"] != row["sales_order_uid"]:
            raise CommerceError(
                409, "invoice_source", "Invoice source does not match this checkout"
            )
        return {
            "status": "void"
            if invoice["state"] == "void"
            else "draft"
            if invoice["state"] == "draft"
            else "paid"
            if Decimal(invoice["remaining"]) == 0
            else "partial"
            if Decimal(invoice["allocated"]) > 0
            else "unpaid",
            "invoice_reference": invoice["name"],
            "invoice_state": invoice["state"],
            "total": invoice["total"],
            "allocated": invoice["allocated"],
            "remaining": invoice["remaining"],
            "message": "Payments recorded in Finance; this website does not process cards or bank transfers.",
        }

    def portal_projection(self, row):
        return {
            "uid": row["uid"],
            "reference": row["name"],
            "state": row["state"],
            "net_total": row["net_total"],
            "currency_code": row["snapshot"]["currency_code"],
            "lines": row["snapshot"]["lines"],
            "payment": self.payment(row),
        }

    def portal_checkout(self, token, uid):
        grant = self.authorize(token)
        rows = self.store.read(
            select(Checkout.__table__)
            .where(Checkout.uid == key(uid), Checkout.grant_uid == key(grant["uid"]))
            .limit(1)
        )
        if not rows:
            raise CommerceError(404, "not_found", "Checkout not found in this portal")
        return self.portal_projection(rows[0])

    def portal_orders(self, token, *, page_index=0, page_size=25):
        grant = self.authorize(token)
        terms = [Checkout.grant_uid == key(grant["uid"])]
        count = int(
            self.store.read(
                select(func.count().label("count")).select_from(Checkout).where(*terms)
            )[0]["count"]
        )
        rows = self.store.read(
            select(Checkout.__table__)
            .where(*terms)
            .order_by(Checkout.created_at.desc(), Checkout.uid)
            .offset(page_index * page_size)
            .limit(page_size),
            max_rows=page_size,
        )
        return {
            "site_uid": grant["site_uid"],
            "expires_at": grant["expires_at"],
            "items": [self.portal_projection(row) for row in rows],
            "pageInfo": {
                "pageIndex": page_index,
                "pageSize": page_size,
                "totalItems": count,
                "hasNextPage": (page_index + 1) * page_size < count,
                "hasPreviousPage": page_index > 0,
            },
        }

    def invoice(self, uid, payload):
        self.require("commerce.manage")
        data = InvoiceInput.model_validate(payload)
        row = self.raw("checkouts", uid)
        if row["invoice_uid"]:
            raise CommerceError(409, "already_invoiced", "This checkout already has an invoice")
        sales = self.same_source(self.dependencies.sales())
        order = sales.get(row["sales_order_uid"])
        finance = self.same_source(self.dependencies.finance())
        invoice_uid, plan = finance.plan_from_sales(
            {
                **data.model_dump(exclude={"expected_version"}),
                "order_uid": row["sales_order_uid"],
                "expected_order_version": order["version"],
            }
        )
        self.transact(
            [
                self.guard(Checkout, row, data.expected_version, {"invoice_uid": invoice_uid}),
                *plan,
                self.audit("checkouts", uid, "invoice", data.expected_version + 1, ["invoice_uid"]),
            ]
        )
        return self.get("checkouts", uid)

    def history(self, resource, uid):
        self.require("commerce.manage")
        self.get(resource, uid)
        return {
            "items": self.store.read(
                select(AuditEvent.__table__)
                .where(AuditEvent.resource == resource, AuditEvent.record_uid == key(uid))
                .order_by(AuditEvent.occurred_at.desc())
                .limit(100)
            )
        }
