"""Start CRM with Base adoption on a pinned, already-activated local DataSource."""

import argparse
import os
from uuid import UUID

from metatables import configure_local_client
from src.erp.base.store import require_local_runtime
from src.erp.crm.base_adoption.store import Store
from src.erp.crm.platform.catalog import CatalogRegistry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-uid", required=True, type=UUID)
    args = parser.parse_args()
    configure_local_client()
    if str(require_local_runtime()) != str(args.source_uid):
        raise RuntimeError("Local DataSource differs from the reviewed source")
    Store(CatalogRegistry(), require_active=True).data_source_uid
    os.environ["CRM_BASE_ADOPTION"] = "1"
    import uvicorn

    from api.erp.crm.local import create_app

    uvicorn.run(create_app(), host="127.0.0.1", port=38641, access_log=False)


if __name__ == "__main__":
    main()
