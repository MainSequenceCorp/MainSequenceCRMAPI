"""Explicit owner read and stock command contracts; no foreign models."""

from functools import wraps

from .errors import ManufacturingError


def translate(fn):
    @wraps(fn)
    def call(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as error:
            if all(hasattr(error, key) for key in ("status", "code", "message")):
                raise ManufacturingError(error.status, error.code, error.message) from error
            raise

    return call


class InventoryPort:
    def __init__(self, service):
        self.service = service

    @property
    def store(self):
        return self.service.store

    @translate
    def require(self, *args):
        return self.service.require(*args)

    @translate
    def get(self, *args):
        return self.service.get(*args)

    @translate
    def stock_policy(self, *args):
        return self.service.stock_policy(*args)

    @translate
    def collection(self, *args, **kwargs):
        return self.service.collection(*args, **kwargs)

    @translate
    def plan_prepare_production(self, *args):
        return self.service.plan_prepare_production(*args)

    @translate
    def plan_transition_production(self, *args):
        return self.service.plan_transition_production(*args)

    @translate
    def plan_finance_production(self, *args):
        return self.service.plan_finance_production(*args)

    @translate
    def production_valuation(self, *args):
        return self.service.production_valuation(*args)


class Dependencies:
    def __init__(self, base, catalog, inventory):
        self.base, self.catalog, self.inventory = base, catalog, inventory

    def ready(self):
        self.base.require("base.read")
        self.catalog.require("catalog.read")
        self.inventory.require("inventory.read")
        return {
            "base": self.base.store.data_source_uid,
            "catalog": self.catalog.store.data_source_uid,
            "inventory": self.inventory.store.data_source_uid,
        }

    def get(self, owner, resource, uid):
        row = {"base": self.base, "catalog": self.catalog, "inventory": self.inventory}[owner].get(
            resource, uid
        )
        if row.get("archived_at"):
            raise ManufacturingError(422, "inactive_reference", "Choose active business references")
        return row

    def collection(self, resource, **query):
        mapping = {
            "companies": (self.base, "operating-companies"),
            "items": (self.catalog, "items"),
            "locations": (self.inventory, "locations"),
        }
        if resource not in mapping:
            raise ManufacturingError(404, "not_found", "Unknown Manufacturing reference")
        owner, key = mapping[resource]
        return owner.collection(key, **query)
