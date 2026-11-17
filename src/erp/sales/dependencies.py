"""Public owner read contracts; Sales never writes its prerequisites' tables."""

import os
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from src.erp.sales.errors import SalesError


class Dependencies:
    def __init__(self, base, catalog, *, local=False):
        self.base, self.catalog, self.local = base, catalog, local

    def ready(self):
        self.base.require("base.read")
        self.catalog.require("catalog.read")
        return {
            "base": self.base.store.data_source_uid,
            "catalog": self.catalog.store.data_source_uid,
        }

    def get(self, owner, resource, uid):
        service = self.base if owner == "base" else self.catalog
        row = service.get(resource, uid)
        if row.get("archived_at"):
            raise SalesError(422, "inactive_reference", f"{resource} reference must be active")
        return row

    def collection(self, resource, **query):
        if resource == "opportunities":
            return self.crm("deals/", params=query)
        mapping = {
            "customers": (self.base, "parties"),
            "companies": (self.base, "operating-companies"),
            "currencies": (self.base, "currencies"),
            "items": (self.catalog, "items"),
        }
        if resource not in mapping:
            raise SalesError(404, "not_found", "Unknown Sales reference")
        service, key = mapping[resource]
        return service.collection(key, **query)

    def crm(self, path, *, params=None):
        # Optional local companion only. No invented hosted endpoint or credential forwarding.
        if not self.local or os.environ.get("SALES_CRM_ENABLED", "true") == "false":
            raise SalesError(
                503, "crm_unavailable", "CRM linking is not configured; Sales works without it"
            )
        origin = os.environ.get("SALES_LOCAL_CRM_ORIGIN", "http://127.0.0.1:38641")
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise SalesError(
                503, "crm_unavailable", "CRM local integration requires an exact loopback origin"
            )
        try:
            response = httpx.get(
                origin.rstrip("/") + "/api/crm/v1/" + path, params=params, timeout=20
            )
        except httpx.HTTPError as exc:
            raise SalesError(
                503, "crm_unavailable", "CRM is unavailable; try again or remove the optional link"
            ) from exc
        if response.status_code != 200:
            raise SalesError(
                response.status_code if response.status_code in {403, 404} else 503,
                "crm_unavailable",
                "The CRM opportunity is unavailable to the signed-in user",
            )
        return response.json()

    def opportunity(self, uid, customer_uid):
        deal = self.crm(f"deals/{UUID(str(uid))}/")
        if deal.get("archived_at"):
            raise SalesError(422, "inactive_opportunity", "Select an active CRM opportunity")
        company_uid = deal.get("company_uid")
        if company_uid:
            company = self.crm(f"companies/{UUID(str(company_uid))}/")
            customer = self.get("base", "parties", customer_uid)
            claim = customer.get("consumers", {}).get("crm", {})
            if company.get("archived_at") or not (
                claim.get("logical") == "company"
                and claim.get("active") is True
                and str(claim.get("uid")) == str(company["uid"])
            ):
                raise SalesError(
                    422,
                    "customer_mismatch",
                    "Customer must match the opportunity company’s shared identity",
                )
        return deal
