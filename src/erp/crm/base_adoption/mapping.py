"""Lossless CRM-to-Base mapping; CRM-only fields never enter the directory."""

from src.erp.base.identity_contracts import IdentityDetails

PERSON_FIELDS = ("first_name", "last_name", "gender", "avatar_ref", "socials")
ORGANIZATION_FIELDS = (
    "website",
    "linkedin_url",
    "normalized_domain",
    "phone_number",
    "address",
    "zipcode",
    "city",
    "state_abbr",
    "country",
    "tax_identifier",
    "logo_ref",
)


def party_input(resource, row):
    person = resource == "contacts"
    fields = PERSON_FIELDS if person else ORGANIZATION_FIELDS
    identity = {key: row.get(key) for key in fields}
    if person:
        identity["name_style"] = "structured"
    emails = row.get("emails", []) if person else []
    phones = row.get("phones", []) if person else []
    identity.update(
        email_labels={item["email"]: item["type"] for item in emails},
        phone_labels={item["number"]: item["type"] for item in phones},
    )
    name = (
        (
            " ".join(str(row.get(key) or "") for key in ("first_name", "last_name")).strip()
            or (emails[0]["email"] if emails else "Unnamed person")
        )
        if person
        else row["name"]
    )
    identity = IdentityDetails.model_validate(identity).model_dump(mode="json", exclude_unset=True)
    if "socials" in identity:
        identity["socials"] = {k: v for k, v in identity["socials"].items() if v is not None}
    return {
        "name": name,
        "kind": "person" if person else "organization",
        "emails": [item["email"] for item in emails],
        "phones": [item["number"] for item in phones],
        "identity": identity,
        "language_uid": None,
    }


def party_projection(resource, party):
    identity = party.get("identity") or {}
    if resource == "contacts":
        result = {key: identity.get(key) for key in PERSON_FIELDS}
        result["socials"] = result["socials"] or {}
        # A Directory-only full name is not guessed into first and last names.
        if (
            identity.get("name_style", "unstructured") == "unstructured"
            and not result["first_name"]
            and not result["last_name"]
        ):
            result["first_name"] = party["name"]
        result["emails"] = [
            {"email": value, "type": identity.get("email_labels", {}).get(value, "other")}
            for value in party["emails"]
        ]
        result["phones"] = [
            {"number": value, "type": identity.get("phone_labels", {}).get(value, "other")}
            for value in party["phones"]
        ]
        return result
    return {"name": party["name"], **{key: identity.get(key) for key in ORGANIZATION_FIELDS}}


def affiliation_input(row):
    return {
        "name": "Employment",
        "person_uid": row["contact_uid"],
        "organization_uid": row["company_uid"],
        "role": "Employment",
        "starts_on": row["started_period"]
        if row.get("started_period") and len(row["started_period"]) == 10
        else None,
        "ends_on": row["ended_period"]
        if row.get("ended_period") and len(row["ended_period"]) == 10
        else None,
        "status": row["status"],
        "started_period": row["started_period"],
        "ended_period": row["ended_period"],
        "job_title": row["job_title"],
    }


def provenance(row):
    return {
        key: row.get(key)
        for key in (
            "created_at",
            "updated_at",
            "created_by_uid",
            "updated_by_uid",
            "source_created_at",
            "source_updated_at",
            "archived_at",
            "version",
        )
    }
