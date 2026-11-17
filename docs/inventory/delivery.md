# Local setup and operations

Before every migration/write batch require actual MetaTables Local mode, SQLite,
active/ready bootstrap and source 75b7fd29-3b1f-565d-be8d-a3a27d643de2. Base and Catalog
must be installed; optional integrations require their own ready schemas.

```bash
.venv/bin/metatables --local runtime status
.venv/bin/python -m scripts.erp.inventory.setup_local --source-uid 75b7fd29-3b1f-565d-be8d-a3a27d643de2
INVENTORY_LOCAL_SOURCE_UID=75b7fd29-3b1f-565d-be8d-a3a27d643de2 .venv/bin/python -m uvicorn api.erp.inventory.local:create_app --factory --host 127.0.0.1 --port 38731 --no-access-log
```

Own provider src.erp.inventory.migrations:migration, namespace erp-inventory,
version table erp_inventory__alembic_version, identifier erp_inventory.alembic_version.
Reviewed revision 0001 contains only six owned tables/constraints/indexes. Applied
revisions are immutable. Startup never migrates; binding validation fails closed.
Finance metadata refresh uses Finance's own existing provider; no new Finance DDL.

Local identity uses the existing SDK sign-in. Launcher requires loopback client,
host and origin, rejects supplied identity headers and refuses a source mismatch.
INVENTORY_SALES_ENABLED=false and INVENTORY_FINANCE_ENABLED=false disable optional
adapters. Owner identity/capability checks run when used. Optional imports are lazy.
Same-source plans fail before writes if owner sources differ.

Frontend transport is verified at local port 38731 through /api/inventory; the
combined artifact and all four Help links pass. Hosted release binding remains pending. No active workflow exists;
the eventual engineering example is inert and requires platform validation after
user approval. Do not push tags, reconcile, deploy or migrate hosted state.

After errors stop writes, inspect runtime/source/bindings and saved records. Read the
original request UUID after uncertain creation or return, current versions after
command uncertainty. Never replay blindly or select a different/hosted source as
recovery. Cleanup is limited to explicit owned disposable fixture UUIDs.
