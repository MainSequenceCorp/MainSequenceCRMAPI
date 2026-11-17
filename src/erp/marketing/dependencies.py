"""Base public identity reads and optional local CRM follow-up verification."""

import json
import os
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from .errors import MarketingError


class Dependencies:
    def __init__(self, base, *, local=False):
        self.base, self.local = base, local

    def ready(self):
        self.base.require("base.read")
        return {"base": self.base.store.data_source_uid}

    def person(self, uid):
        row = self.base.get("parties", uid)
        if row["kind"] != "person" or row.get("archived_at"):
            raise MarketingError(422, "inactive_person", "Choose an active shared person")
        return row

    def people(self, **query):
        return self.base.collection("parties", kind="person", **query)

    @property
    def crm_enabled(self):
        return self.local and os.environ.get("MARKETING_CRM_ENABLED", "true") != "false"

    def crm(self, path, *, params=None):
        if not self.crm_enabled:
            raise MarketingError(
                503,
                "crm_unavailable",
                "CRM follow-up linking is unavailable; mailings work independently",
            )
        origin = os.environ.get("MARKETING_LOCAL_CRM_ORIGIN", "http://127.0.0.1:38641")
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
            raise MarketingError(
                503, "crm_unavailable", "CRM local integration requires an exact loopback origin"
            )
        try:
            response = httpx.get(
                origin.rstrip("/") + "/api/crm/v1/" + path, params=params, timeout=20
            )
        except httpx.HTTPError as exc:
            raise MarketingError(503, "crm_unavailable", "CRM is unavailable") from exc
        if response.status_code != 200:
            raise MarketingError(
                response.status_code if response.status_code in {403, 404} else 503,
                "crm_unavailable",
                "CRM follow-up is unavailable to the signed-in user",
            )
        return response.json()

    def contact_uid(self, party_uid):
        person = self.person(party_uid)
        claim = person.get("consumers", {}).get("crm", {})
        if (
            claim.get("logical") != "contact"
            or claim.get("active") is not True
            or not claim.get("uid")
        ):
            raise MarketingError(
                422, "crm_contact", "Adopt this person into CRM before linking a follow-up"
            )
        return str(UUID(str(claim["uid"])))

    def followup(self, task_uid, party_uid):
        task = self.crm(f"tasks/{UUID(str(task_uid))}/")
        contact = self.contact_uid(party_uid)
        if task.get("archived_at") or str(task["contact_uid"]) != contact:
            raise MarketingError(
                422, "followup_mismatch", "Choose an active task for this subscriber's CRM Contact"
            )
        self.crm(f"contacts/{contact}/")
        return task

    def tasks(self, party_uid, **query):
        return self.crm(
            "tasks/",
            params={**query, "filters": json.dumps({"contact_uid": self.contact_uid(party_uid)})},
        )
