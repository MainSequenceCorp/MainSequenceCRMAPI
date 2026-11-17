"""Public owner reads and optional integration factories, without foreign models."""

from .errors import ProjectsError


class Dependencies:
    def __init__(self, base, sales_factory=None, finance_factory=None):
        self.base, self.sales_factory, self.finance_factory = base, sales_factory, finance_factory

    def ready(self):
        self.base.require("base.read")
        return {"base": self.base.store.data_source_uid}

    def base_record(self, resource, uid):
        row = self.base.get(resource, uid)
        if row.get("archived_at"):
            raise ProjectsError(422, "inactive_reference", "Choose active shared records")
        return row

    def sales(self):
        if self.sales_factory is None:
            raise ProjectsError(
                503,
                "sales_unavailable",
                "Sales integration is unavailable; standalone Projects remains available",
            )
        return self.sales_factory()

    def finance(self):
        if self.finance_factory is None:
            raise ProjectsError(
                503,
                "finance_unavailable",
                "Finance billing is unavailable; project delivery remains available",
            )
        return self.finance_factory()

    def collection(self, resource, **query):
        if resource == "orders":
            return self.sales().collection(**query)
        if resource not in {"parties", "people", "companies"}:
            raise ProjectsError(404, "not_found", "Unknown reference")
        return self.base.collection(
            "operating-companies" if resource == "companies" else "parties",
            **query,
            **({"kind": "person"} if resource == "people" else {}),
        )
