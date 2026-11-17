"""Explicitly apply People's own provider to the reviewed local source."""

import argparse

from metatables import configure_local_client, upgrade_application
from src.erp.people.store import require_local_runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-uid", required=True)
    args = parser.parse_args()
    configure_local_client()
    if str(require_local_runtime()) != args.source_uid:
        raise RuntimeError("Unexpected local DataSource; no migration applied")
    result = upgrade_application("src.erp.people.migrations:migration")
    print({"revision": result["revision"], "data_source_uid": args.source_uid, "local": True})


if __name__ == "__main__":
    main()
