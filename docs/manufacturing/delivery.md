# Local deployment and recovery

Authorized storage is ready MetaTables Local SQLite, exact source
`75b7fd29-3b1f-565d-be8d-a3a27d643de2`. Verify local_mode true, dialect/class_type sqlite,
active/ready bootstrap and exact source before any writes. Loopback alone is not proof.

```bash
.venv/bin/metatables --local runtime status
.venv/bin/python -m scripts.erp.inventory.setup_local --source-uid 75b7fd29-3b1f-565d-be8d-a3a27d643de2
.venv/bin/python -m scripts.erp.manufacturing.setup_local --source-uid 75b7fd29-3b1f-565d-be8d-a3a27d643de2
MANUFACTURING_LOCAL_SOURCE_UID=75b7fd29-3b1f-565d-be8d-a3a27d643de2 .venv/bin/python -m uvicorn api.erp.manufacturing.local:create_app --factory --host 127.0.0.1 --port 38751 --no-access-log
```

Base/Catalog/Inventory are prerequisites. Inventory's own revision 0002 adds nullable
manufacturing_order_uid and named uniqueness to Move plus production location usage;
its applied 0001 remains unchanged. Manufacturing revision 0001 owns five models,
provider src.erp.manufacturing.migrations:migration and version table
erp_manufacturing__alembic_version. Finance remains at 0002. Migrations never run at
API startup. Restart local Inventory and consumers (Purchasing/Manufacturing) after
Inventory upgrade. All coordinated plans must use the same governed source.

The loopback launcher checks host/client/origin, rejects forged identity headers and
reuses SDK sign-in. MANUFACTURING_FINANCE_ENABLED=false disables the optional handoff.
Platform Team mappings use MANUFACTURING_READER/WRITER/MANAGER/ADMIN_TEAM_UIDS.

Frontend proxy /api/manufacturing → 38751. VITE_MANUFACTURING_ENABLED controls inclusion;
future hosted VITE_MANUFACTURING_FASTAPI_RELEASE_UID must be explicitly approved.
No credentials belong in browser config. One ERP artifact and /docs/ include all modules.

Reload on conflict; inspect original UUID/status on uncertain writes. Do not reverse
individual production movements. Fixture cleanup uses exact disposable UUIDs through
each owner's governed tables and removes stock/Finance children before parents.

The workflow candidate remains outside .mainsequence/workflows, matching only
-manufacturing tags and its own migration job. Inventory prerequisite must release
separately in an approved sequence. Platform identity, hosted engine, delegation,
tag selection and deployment remain unverified. No push/tag/hosted migration or
platform deployment without explicit user approval.
