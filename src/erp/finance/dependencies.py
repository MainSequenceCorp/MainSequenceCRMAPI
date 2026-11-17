"""Public Base reads and an explicitly optional Sales integration port."""

from .errors import FinanceError


class Dependencies:
    def __init__(self, base, sales_factory=None):
        self.base, self.sales_factory = base, sales_factory

    def ready(self):
        self.base.require("base.read")
        return {"base": self.base.store.data_source_uid}

    def get(self, resource, uid):
        row = self.base.get(resource, uid)
        if row.get("archived_at"):
            raise FinanceError(422, "inactive_reference", f"{resource} reference must be active")
        return row

    def sales(self):
        if self.sales_factory is None:
            raise FinanceError(
                503,
                "sales_unavailable",
                "Sales linking is disabled; independent Finance remains available",
            )
        return self.sales_factory()

    def collection(self, resource, **query):
        if resource == "orders":
            return self.sales().collection(state="confirmed", **query)
        mapping = {
            "parties": "parties",
            "companies": "operating-companies",
            "currencies": "currencies",
        }
        if resource not in mapping:
            raise FinanceError(404, "not_found", "Unknown Finance reference")
        return self.base.collection(mapping[resource], **query)
