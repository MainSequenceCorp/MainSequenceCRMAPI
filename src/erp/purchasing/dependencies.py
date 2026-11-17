"""Public prerequisite reads and lazy optional owners; no foreign storage writes."""

from .errors import PurchasingError


class Dependencies:
    def __init__(self, base, catalog, inventory_factory=None, finance_factory=None):
        self.base, self.catalog = base, catalog
        self.inventory_factory, self.finance_factory = inventory_factory, finance_factory

    def ready(self):
        self.base.require("base.read")
        self.catalog.require("catalog.read")
        return {
            "base": self.base.store.data_source_uid,
            "catalog": self.catalog.store.data_source_uid,
        }

    def get(self, owner, resource, uid):
        row = (self.base if owner == "base" else self.catalog).get(resource, uid)
        if row.get("archived_at"):
            raise PurchasingError(
                422, "inactive_reference", "Choose active shared reference records"
            )
        return row

    def inventory(self):
        if self.inventory_factory is None:
            raise PurchasingError(
                503,
                "inventory_unavailable",
                "Inventory is unavailable; service purchasing remains independent",
            )
        return self.inventory_factory()

    def finance(self):
        if self.finance_factory is None:
            raise PurchasingError(
                503, "finance_unavailable", "Finance is unavailable; purchasing remains independent"
            )
        return self.finance_factory()

    def collection(self, resource, **query):
        if resource in {"stock-items", "locations"}:
            return self.inventory().collection(resource, **query)
        mapping = {
            "suppliers": (self.base, "parties"),
            "companies": (self.base, "operating-companies"),
            "currencies": (self.base, "currencies"),
            "items": (self.catalog, "items"),
        }
        if resource not in mapping:
            raise PurchasingError(404, "not_found", "Unknown Purchasing reference")
        owner, key = mapping[resource]
        return owner.collection(key, **query)
