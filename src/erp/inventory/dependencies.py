"""Explicit public-owner reads; no foreign business tables."""

from .errors import InventoryError


class Dependencies:
    def __init__(self, base, catalog, sales_factory=None, finance_factory=None):
        self.base, self.catalog, self.sales_factory, self.finance_factory = (
            base,
            catalog,
            sales_factory,
            finance_factory,
        )

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
            raise InventoryError(
                422, "inactive_reference", "Choose active shared reference records"
            )
        return row

    def sales(self):
        if self.sales_factory is None:
            raise InventoryError(
                503,
                "sales_unavailable",
                "Sales fulfillment is unavailable; standalone stock operations remain available",
            )
        return self.sales_factory()

    def finance(self):
        if self.finance_factory is None:
            raise InventoryError(
                503,
                "finance_unavailable",
                "Finance valuation is unavailable; stock operations remain independent",
            )
        return self.finance_factory()

    def collection(self, resource, **query):
        if resource == "orders":
            return self.sales().collection(state="confirmed", **query)
        if resource == "companies":
            return self.base.collection("operating-companies", **query)
        if resource == "items":
            return self.catalog.collection("items", **query)
        raise InventoryError(404, "not_found", "Unknown Inventory reference")
