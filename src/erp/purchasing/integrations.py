"""Lazy authorized owner commands; never import foreign models."""

from functools import wraps

from .errors import PurchasingError


def translate(fn):
    @wraps(fn)
    def call(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as error:
            if all(hasattr(error, key) for key in ("status", "code", "message")):
                raise PurchasingError(error.status, error.code, error.message) from error
            raise

    return call


class OwnerPort:
    def __init__(self, service):
        self.service = service

    @property
    def store(self):
        return self.service.store

    @translate
    def collection(self, *args, **query):
        return self.service.collection(*args, **query)

    @translate
    def get_movement(self, uid):
        return self.service.get("movements", uid)

    @translate
    def plan_purchase_receipt(self, *args):
        return self.service.plan_purchase_receipt(*args)

    @translate
    def plan_received_guard(self, *args):
        return self.service.plan_received_guard(*args)

    @translate
    def plan_from_purchase(self, *args):
        return self.service.plan_from_purchase(*args)


def configured_inventory(*, local, base, catalog):
    from api.erp.inventory.identity import actor_and_capabilities
    from src.erp.inventory.dependencies import Dependencies
    from src.erp.inventory.service import Service
    from src.erp.inventory.store import Store

    actor, caps = actor_and_capabilities(local=local)
    return OwnerPort(Service(Store(local_only=local), actor, caps, Dependencies(base, catalog)))


def configured_finance(*, local, base):
    from api.erp.finance.identity import actor_and_capabilities
    from src.erp.finance.dependencies import Dependencies
    from src.erp.finance.service import Service
    from src.erp.finance.store import Store

    actor, caps = actor_and_capabilities(local=local)
    return OwnerPort(Service(Store(local_only=local), actor, caps, Dependencies(base)))
