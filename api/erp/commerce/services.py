"""Composition of public owner contracts; optional modules remain lazy."""

import os

from api.erp.base.identity import actor_and_capabilities as base_identity
from api.erp.catalog.identity import actor_and_capabilities as catalog_identity
from src.erp.base.service import Service as BaseService
from src.erp.base.store import Store as BaseStore
from src.erp.catalog.service import Service as CatalogService
from src.erp.catalog.store import Store as CatalogStore
from src.erp.commerce.dependencies import Dependencies, OwnerPort
from src.erp.commerce.service import Service
from src.erp.commerce.store import Store

from .identity import actor_and_capabilities


def enabled(owner):
    return os.environ.get("COMMERCE_" + owner.upper() + "_ENABLED", "true") != "false"


def service(*, local=False, store=None):
    actor, caps = actor_and_capabilities(local=local)
    ba, bc = base_identity(local=local)
    ca, cc = catalog_identity(local=local)
    base = BaseService(BaseStore(local_only=local), ba, bc)
    catalog = CatalogService(CatalogStore(local_only=local), ca, cc)

    def sales():
        from api.erp.sales.identity import actor_and_capabilities
        from src.erp.sales.dependencies import Dependencies
        from src.erp.sales.service import Service
        from src.erp.sales.store import Store

        a, c = actor_and_capabilities(local=local)
        return OwnerPort(
            Service(Store(local_only=local), a, c, Dependencies(base, catalog, local=local))
        )

    def finance():
        from api.erp.finance.identity import actor_and_capabilities
        from src.erp.finance.dependencies import Dependencies
        from src.erp.finance.service import Service
        from src.erp.finance.store import Store

        a, c = actor_and_capabilities(local=local)
        return OwnerPort(
            Service(
                Store(local_only=local),
                a,
                c,
                Dependencies(base, sales_factory=sales if enabled("sales") else None),
            )
        )

    return Service(
        store or Store(local_only=local),
        actor,
        caps,
        Dependencies(
            base,
            catalog,
            sales if enabled("sales") else None,
            finance if enabled("finance") else None,
        ),
    )
