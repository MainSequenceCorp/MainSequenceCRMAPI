"""Load active MetaTable bindings for module-owned validation."""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from itertools import batched

from metatables import MetaTable

# Stay below the catalog page size so each batch is one request.
CATALOG_BATCH_SIZE = 80


def active_catalog_rows(identifiers, *, catalog=None):
    if catalog is None:
        return MetaTable.filter(identifier__in=list(identifiers), provisioning_status="active")
    return [row for identifier in identifiers for row in catalog.get(identifier, ())]


def load_active_catalog(identifiers):
    batches = tuple(batched(sorted(set(identifiers)), CATALOG_BATCH_SIZE))
    if not batches:
        return {}

    catalog = defaultdict(list)
    # A large release needs multiple pages. Fetch at most two at once and
    # propagate the request's SDK authority and deadline to each worker.
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [pool.submit(copy_context().run, active_catalog_rows, batch) for batch in batches]
        for result in pending:
            for row in result.result():
                catalog[row.identifier].append(row)
    return catalog
