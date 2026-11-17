"""CRM-owned compatibility projection contributed to a Base transaction."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update

from metatables.compiled_sql.v1 import GuardedStatement
from src.erp.base.service import BaseError
from src.erp.crm.metatables import MODELS

from .mapping import party_projection


def consumer(store):
    def contribute(resource, old, new, actor_uid, claim):
        logical = claim["logical"]
        table = MODELS[logical].__table__
        uid = UUID(str(claim["uid"]))
        rows = store.read(select(table).where(table.c.uid == uid))
        if not rows:
            raise BaseError(409, "missing_consumer", "The linked CRM profile is missing")
        current = rows[0]
        if resource == "parties":
            values = party_projection("contacts" if logical == "contact" else "companies", new)
            from pydantic import ValidationError

            from src.erp.crm.models.companies import CompanyCreate
            from src.erp.crm.models.contacts import ContactCreate

            contract = ContactCreate if logical == "contact" else CompanyCreate
            try:
                candidate = {key: current[key] for key in contract.model_fields if key in current}
                candidate.update(values)
                candidate.pop("normalized_domain", None)
                contract.model_validate(candidate)
            except ValidationError as error:
                raise BaseError(
                    422,
                    "consumer_contract",
                    "These identity values are incompatible with the linked CRM profile",
                ) from error
            if logical == "contact" and not (
                values["first_name"] or values["last_name"] or values["emails"]
            ):
                raise BaseError(422, "invalid_identity", "A CRM person needs a name or email")
        elif resource == "affiliations":
            if str(new["person_uid"]) != str(current["contact_uid"]) or str(
                new["organization_uid"]
            ) != str(current["company_uid"]):
                raise BaseError(
                    422,
                    "immutable_relationship",
                    "Change the relationship through the CRM transition command",
                )
            if current["is_primary"] and (new["status"] != "current" or new.get("archived_at")):
                raise BaseError(
                    409,
                    "primary_relationship",
                    "Change the primary company in CRM before ending this relationship",
                )
            values = {
                key: new.get(key)
                for key in ("status", "started_period", "ended_period", "job_title", "archived_at")
            }
            if isinstance(values["archived_at"], str):
                values["archived_at"] = datetime.fromisoformat(values["archived_at"])
        else:
            raise BaseError(422, "unsupported_consumer", "CRM cannot project this resource")
        values.update(
            version=current["version"] + 1,
            updated_at=datetime.now(timezone.utc),
            updated_by_uid=actor_uid,
        )
        steps = [
            GuardedStatement(
                update(table)
                .where(table.c.uid == uid, table.c.version == current["version"])
                .values(**values),
                expect_rows=1,
                label="crm_projection_version",
            )
        ]
        if resource == "affiliations":
            contact = MODELS["contact"].__table__
            steps.append(
                update(contact)
                .where(contact.c.uid == UUID(str(current["contact_uid"])))
                .values(
                    version=contact.c.version + 1,
                    updated_at=values["updated_at"],
                    updated_by_uid=actor_uid,
                )
            )
        return steps

    return contribute
