"""Optional adapter to Sales-owned operations; no Sales storage imports."""

from functools import wraps

from .errors import FinanceError


def translate(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        from src.erp.sales.errors import SalesError

        try:
            return function(*args, **kwargs)
        except SalesError as error:
            raise FinanceError(error.status, "sales_" + error.code, error.message) from error

    return wrapped


class SalesPort:
    def __init__(self, service):
        self.service = service
        self.store = service.store

    @translate
    def get(self, uid):
        return self.service.get(uid)

    @translate
    def collection(self, **query):
        return self.service.collection(**query)

    @translate
    def plan_attach(self, *args):
        return self.service.plan_attach(*args)


def configured_sales(*, local=False):
    from api.erp.sales.identity import actor_and_capabilities
    from src.erp.sales.service import Service
    from src.erp.sales.store import Store

    actor, capabilities = actor_and_capabilities(local=local)
    # Only confirmed Sales reads and its linking plan are used. No product or
    # identity mutation is delegated through this adapter.
    return SalesPort(Service(Store(local_only=local), actor, capabilities, None))
