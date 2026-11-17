"""CRM integration with public Base command plans, never independent Base SQL writes."""

from uuid import UUID

from sqlalchemy import select

from src.erp.base.metatables import Affiliation, Party
from src.erp.base.service import Service

from .mapping import affiliation_input, party_input, provenance
from .projector import consumer

CAPABILITIES = {"base.read", "base.write"}


def service(store, actor_uid):
    return Service(store, actor_uid, CAPABILITIES, consumers={"crm": consumer(store)})


def identity_plan(store, actor_uid, resource, row, *, extracting=False):
    uid = UUID(str(row["uid"]))
    is_party = resource in ("contacts", "companies")
    base_resource = "parties" if is_party else "affiliations"
    table = (Party if is_party else Affiliation).__table__
    existing = store.read(select(table).where(table.c.uid == uid))
    payload = party_input(resource, row) if is_party else affiliation_input(row)
    logical = (
        "contact"
        if resource == "contacts"
        else "company"
        if resource == "companies"
        else "contact_company_affiliation"
    )
    claims = {
        "crm": {"logical": logical, "uid": str(uid), "active": row.get("archived_at") is None}
    }
    current = existing[0] if existing else None
    if current:
        if "crm" not in current.get("consumers", {}):
            raise ValueError("Base identity UUID collision: explicit adoption is required")
        claims = {**current["consumers"], **claims}
        if is_party:
            payload["language_uid"] = current["language_uid"]
            if resource == "companies":
                # CRM has only one main phone; Directory lists and labels are separate.
                payload["emails"], payload["phones"] = current["emails"], current["phones"]
                payload["identity"].pop("email_labels", None)
                payload["identity"].pop("phone_labels", None)
            if (
                resource == "contacts"
                and current.get("identity", {}).get("name_style", "unstructured") == "unstructured"
                and row.get("first_name") == current["name"]
                and not row.get("last_name")
            ):
                payload["identity"].update(
                    name_style="unstructured", first_name=None, last_name=None
                )
            # Preserve fields outside CRM's shared subset.
            payload["identity"] = {**current.get("identity", {}), **payload["identity"]}
    steps, _ = service(store, actor_uid).plan_save(
        base_resource,
        payload,
        uid=uid if current else None,
        create_uid=uid,
        expected_version=current["version"] if current else None,
        skip_consumer="crm",
        claims=claims,
        provenance=provenance(row) if extracting else None,
        initial_archived_at=row.get("archived_at") if extracting and not is_party else None,
    )
    return steps
