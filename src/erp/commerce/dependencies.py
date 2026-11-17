"""Explicit public owner read contracts and lazy optional commercial owners."""

from functools import wraps

from .errors import CommerceError


def translate(fn):
    @wraps(fn)
    def call(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if all(hasattr(e, k) for k in ("status", "code", "message")):
                raise CommerceError(e.status, e.code, e.message) from e
            raise

    return call


class OwnerPort:
    def __init__(self, service):
        self.service = service

    @property
    def store(self):
        return self.service.store

    @translate
    def get(self, *args):
        return self.service.get(*args)

    @translate
    def collection(self, *args, **kwargs):
        return self.service.collection(*args, **kwargs)

    @translate
    def plan_commerce_checkout(self, *args, **kwargs):
        return self.service.plan_commerce_checkout(*args, **kwargs)

    @translate
    def plan_attach(self, *args):
        return self.service.plan_attach(*args)

    @translate
    def plan_from_sales(self, *args):
        return self.service.plan_from_sales(*args)


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
            raise CommerceError(422, "inactive_reference", "Choose active business references")
        return row

    def sales(self):
        if not self.sales_factory:
            raise CommerceError(
                503,
                "sales_unavailable",
                "Sales checkout is unavailable; published pages remain available",
            )
        return self.sales_factory()

    def finance(self):
        if not self.finance_factory:
            raise CommerceError(
                503, "finance_unavailable", "Finance is unavailable; the order remains retained"
            )
        return self.finance_factory()

    def collection(self, resource, **query):
        mapping = {
            "companies": (self.base, "operating-companies"),
            "currencies": (self.base, "currencies"),
            "customers": (self.base, "parties"),
            "items": (self.catalog, "items"),
        }
        if resource not in mapping:
            raise CommerceError(404, "not_found", "Unknown Commerce reference")
        owner, key = mapping[resource]
        return owner.collection(key, **query)
