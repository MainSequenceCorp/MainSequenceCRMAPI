"""Application-level identity consumers; individual domains stay independent."""

from functools import lru_cache


@lru_cache(maxsize=8)
def identity_consumers(store):
    from src.erp.crm.base_adoption.runtime import enabled

    if not enabled():
        return {}
    from src.erp.crm.base_adoption.projector import consumer
    from src.erp.crm.base_adoption.store import Store
    from src.erp.crm.platform.catalog import configured_registry

    if str(Store(configured_registry(), require_active=True).data_source_uid) != str(
        store.data_source_uid
    ):
        raise RuntimeError("CRM and Base require the same governed DataSource")
    return {"crm": consumer(store)}
