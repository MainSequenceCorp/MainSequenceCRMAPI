"""Resumable, version-fenced extraction using module-owned public commands."""

import json
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, select, update

from metatables.compiled_sql.v1 import GuardedStatement
from src.erp.base.metatables import Affiliation, Party

from .commands import identity_plan
from .mapping import affiliation_input, party_input, party_projection, provenance
from .reads import table
from .resources import link_statement

RESOURCES = {
    "companies": "company",
    "contacts": "contact",
    "affiliations": "contact_company_affiliation",
}


def canonical(resource, row):
    return party_input(resource, row) if resource != "affiliations" else affiliation_input(row)


def digest(payload):
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class Extraction:
    def __init__(self, store, actor_uid, *, selection=None):
        self.store, self.actor = store, UUID(str(actor_uid))
        self.selection = selection

    def rows(self, resource, *, batch_size=100):
        source = table(RESOURCES[resource])
        after = None
        while True:
            query = select(source).order_by(source.c.uid).limit(batch_size)
            if self.selection is not None:
                query = query.where(
                    source.c.uid.in_([UUID(str(uid)) for uid in self.selection.get(resource, [])])
                )
            if after:
                query = query.where(source.c.uid > after)
            batch = self.store.read(query, max_rows=batch_size)
            if not batch:
                return
            yield from batch
            after = UUID(batch[-1]["uid"])

    def inventory(self):
        result = {}
        for resource in RESOURCES:
            count, checksum = 0, sha256()
            for row in self.rows(resource):
                checksum.update(
                    f"{row['uid']}:{row['version']}:{digest(canonical(resource, row))}\n".encode()
                )
                count += 1
            result[resource] = {"count": count, "digest": checksum.hexdigest()}
        return result

    def copy(self):
        counts = {"copied": 0, "unchanged": 0}
        links = table("base_identity_link")
        for resource, logical in RESOURCES.items():
            source = table(logical)
            for row in self.rows(resource):
                uid, payload = UUID(row["uid"]), canonical(resource, row)
                previous = self.store.read(
                    select(links).where(links.c.resource == resource, links.c.record_uid == uid)
                )
                if previous:
                    link = previous[0]
                    if link["state"] == "active":
                        counts["unchanged"] += 1
                        continue
                    if link["source_version"] != row["version"] or link["source_digest"] != digest(
                        payload
                    ):
                        raise ValueError(
                            "Source changed during extraction; reconcile before resuming"
                        )
                    self.reconcile_row(resource, row)
                    counts["unchanged"] += 1
                    continue
                base_table = (Party if resource != "affiliations" else Affiliation).__table__
                if self.store.read(select(base_table.c.uid).where(base_table.c.uid == uid)):
                    raise ValueError(
                        "Target UUID collision; extraction will not overwrite a Directory record"
                    )
                steps = [
                    GuardedStatement(
                        select(source.c.uid)
                        .where(source.c.uid == uid, source.c.version == row["version"])
                        .with_for_update(),
                        expect_rows=1,
                        label="extraction_source_version",
                    )
                ]
                steps.extend(identity_plan(self.store, self.actor, resource, row, extracting=True))
                steps.append(link_statement(self.actor, resource, row, state="copied"))
                self.store.write(steps)
                counts["copied"] += 1
        return counts

    def reconcile_row(self, resource, row):
        target = (Party if resource != "affiliations" else Affiliation).__table__
        rows = self.store.read(select(target).where(target.c.uid == UUID(row["uid"])))
        if not rows:
            raise ValueError("Missing Base identity during reconciliation")
        if resource != "affiliations":
            actual = party_projection(resource, rows[0])
            expected = {key: row.get(key) for key in actual}
        else:
            expected = canonical(resource, row)
            actual = {key: rows[0][key] for key in expected}
        if digest(actual) != digest(expected):
            raise ValueError(f"{resource} identity does not reconcile: {row['uid']}")
        return rows[0]

    def reconcile(self):
        links = table("base_identity_link")
        counts = {}
        for resource in RESOURCES:
            count = 0
            for row in self.rows(resource):
                linked = self.store.read(
                    select(links).where(
                        links.c.resource == resource, links.c.record_uid == UUID(row["uid"])
                    )
                )
                if len(linked) != 1 or linked[0]["base_uid"] != row["uid"]:
                    raise ValueError("CRM record is not linked to its preserved Base identity")
                target = self.reconcile_row(resource, row)
                claim = target.get("consumers", {}).get("crm", {})
                if claim.get("uid") != row["uid"] or claim.get("active") != (
                    row.get("archived_at") is None
                ):
                    raise ValueError("CRM consumer claim does not reconcile")
                if resource == "affiliations" and target.get("archived_at") != row.get(
                    "archived_at"
                ):
                    raise ValueError("Affiliation archive state does not reconcile")
                if linked[0]["state"] == "copied" and digest(target["provenance"]) != digest(
                    provenance(row)
                ):
                    raise ValueError("Extraction provenance does not reconcile")
                count += 1
            query = (
                select(func.count().label("count"))
                .select_from(links)
                .where(links.c.resource == resource, links.c.state != "retired")
            )
            if self.selection is not None:
                query = query.where(
                    links.c.record_uid.in_(
                        [UUID(str(uid)) for uid in self.selection.get(resource, [])]
                    )
                )
            extra = self.store.read(query)[0]["count"]
            if int(extra) != count:
                raise ValueError("Extraction has orphaned or duplicate CRM links")
            counts[resource] = count
        return counts

    def activate(self, expected_inventory):
        if self.inventory() != expected_inventory:
            raise ValueError("CRM changed after the extraction inventory; keep writers stopped")
        counts = self.reconcile()
        links = table("base_identity_link")
        command = update(links).where(links.c.state == "copied")
        if self.selection is not None:
            command = command.where(
                links.c.record_uid.in_(
                    [UUID(str(uid)) for ids in self.selection.values() for uid in ids]
                )
            )
        self.store.write([command.values(state="active")])
        return counts
