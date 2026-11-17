"""Lazy owner-authorized optional adapters; no foreign storage models."""

from functools import wraps

from .errors import InventoryError


def translate(fn):
    @wraps(fn)
    def call(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as error:
            if all(hasattr(error, key) for key in ("status", "code", "message")):
                raise InventoryError(error.status, error.code, error.message) from error
            raise

    return call


class OwnerPort:
    def __init__(self, service):
        self.service = service

    @property
    def store(self):
        return self.service.store

    @translate
    def collection(self, **query):
        return self.service.collection(**query)

    @translate
    def get(self, uid):
        return self.service.get(uid)

    @translate
    def plan_attach(self, *args):
        return self.service.plan_attach(*args)

    @translate
    def plan_inventory_valuation(self, *args):
        return self.service.plan_inventory_valuation(*args)

    @translate
    def inventory_valuation(self, *args):
        return self.service.inventory_valuation(*args)


def configured_sales(*, local):
    from api.erp.sales.identity import actor_and_capabilities
    from src.erp.sales.service import Service
    from src.erp.sales.store import Store

    actor, caps = actor_and_capabilities(local=local)
    return OwnerPort(Service(Store(local_only=local), actor, caps, None))


def configured_finance(*, local):
    from api.erp.base.identity import actor_and_capabilities as base_identity
    from api.erp.finance.identity import actor_and_capabilities
    from src.erp.base.service import Service as BaseService
    from src.erp.base.store import Store as BaseStore
    from src.erp.finance.dependencies import Dependencies
    from src.erp.finance.service import Service
    from src.erp.finance.store import Store

    actor, caps = actor_and_capabilities(local=local)
    ba, bc = base_identity(local=local)
    return OwnerPort(
        Service(
            Store(local_only=local),
            actor,
            caps,
            Dependencies(BaseService(BaseStore(local_only=local), ba, bc)),
        )
    )
