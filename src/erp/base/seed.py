"""Explicit, repeatable starter reference data; never overwrites operator edits."""

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import insert, select

from src.erp.base.metatables import RESOURCES

STARTERS = {
    "countries": [
        {"code": code, "name": name}
        for code, name in [
            ("AT", "Austria"),
            ("DE", "Germany"),
            ("GB", "United Kingdom"),
            ("US", "United States"),
        ]
    ],
    "languages": [
        {"code": code, "name": name}
        for code, name in [
            ("en", "English"),
            ("de", "German"),
            ("es", "Spanish"),
            ("fr", "French"),
            ("it", "Italian"),
        ]
    ],
    "currencies": [
        {
            "code": code,
            "name": name,
            "symbol": symbol,
            "minor_units": places,
            "rounding": "half_even",
        }
        for code, name, symbol, places in [
            ("EUR", "Euro", "€", 2),
            ("USD", "US dollar", "$", 2),
            ("GBP", "Pound sterling", "£", 2),
            ("JPY", "Yen", "¥", 0),
        ]
    ],
}


def seed(service):
    service.require("base.configure")
    counts = {}
    for resource, records in STARTERS.items():
        table = RESOURCES[resource].__table__
        count = 0
        for record in records:
            uid = uuid5(NAMESPACE_URL, f"erp-base:starter:{resource}:{record['code']}")
            if service.store.read(select(table.c.uid).where(table.c.code == record["code"])):
                continue
            now = datetime.now(timezone.utc)
            values = {
                **record,
                "uid": uid,
                "version": 1,
                "created_at": now,
                "updated_at": now,
                "created_by_uid": service.actor_uid,
                "updated_by_uid": service.actor_uid,
                "archived_at": None,
            }
            service.transact(
                [insert(table).values(**values), service.audit(resource, uid, "create", 1, record)]
            )
            count += 1
        counts[resource] = count
    if not service.collection("settings")["items"]:
        service.save("settings", {"name": "Shared defaults", "timezone": "UTC"})
    return counts
