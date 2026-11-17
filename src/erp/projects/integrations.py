"""Optional owner-authorized service adapters; no foreign models or independent writes."""

from functools import wraps

from .errors import ProjectsError


def translate(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception as error:
            if all(hasattr(error, key) for key in ("status", "code", "message")):
                raise ProjectsError(error.status, error.code, error.message) from error
            raise

    return wrapped


class SalesPort:
    def __init__(self, service, catalog):
        self.service, self.catalog = service, catalog

    @property
    def store(self):
        return self.service.store

    @translate
    def collection(self, **query):
        return self.service.collection(state="confirmed", **query)

    @translate
    def service_order(self, uid):
        order = self.service.get(uid)
        if not order["lines"]:
            raise ProjectsError(422, "empty_order", "The service order requires at least one line")
        for line in order["lines"]:
            item = self.catalog.get("items", line["item_uid"])
            if item["kind"] != "service" or item.get("archived_at"):
                raise ProjectsError(
                    422, "service_order", "Choose an order containing active service items only"
                )
        return order

    @translate
    def plan_attach(self, *args):
        return self.service.plan_attach(*args)


class FinancePort:
    def __init__(self, service):
        self.service = service

    @property
    def store(self):
        return self.service.store

    @translate
    def plan_invoice(self, order_uid, payload):
        order = self.service.dependencies.sales().get(order_uid)
        _, statements = self.service.plan_from_sales(
            {**payload, "order_uid": order_uid, "expected_order_version": order["version"]}
        )
        return statements


def configured_sales(*, local):
    from api.erp.catalog.identity import actor_and_capabilities as catalog_identity
    from api.erp.sales.identity import actor_and_capabilities as sales_identity
    from src.erp.catalog.service import Service as CatalogService
    from src.erp.catalog.store import Store as CatalogStore
    from src.erp.sales.service import Service as SalesService
    from src.erp.sales.store import Store as SalesStore

    actor, caps = sales_identity(local=local)
    cat_actor, cat_caps = catalog_identity(local=local)
    return SalesPort(
        SalesService(SalesStore(local_only=local), actor, caps, None),
        CatalogService(CatalogStore(local_only=local), cat_actor, cat_caps),
    )


def configured_finance(*, local):
    from api.erp.base.identity import actor_and_capabilities as base_identity
    from api.erp.finance.identity import actor_and_capabilities as finance_identity
    from src.erp.base.service import Service as BaseService
    from src.erp.base.store import Store as BaseStore
    from src.erp.finance.dependencies import Dependencies as FinanceDependencies
    from src.erp.finance.sales_integration import configured_sales as finance_sales
    from src.erp.finance.service import Service as FinanceService
    from src.erp.finance.store import Store as FinanceStore

    actor, caps = finance_identity(local=local)
    base_actor, base_caps = base_identity(local=local)
    return FinancePort(
        FinanceService(
            FinanceStore(local_only=local),
            actor,
            caps,
            FinanceDependencies(
                BaseService(BaseStore(local_only=local), base_actor, base_caps),
                lambda: finance_sales(local=local),
            ),
        )
    )
