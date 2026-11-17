# Local deployment and recovery

Only verified ready MetaTables Local SQLite is authorized. Exact source:
75b7fd29-3b1f-565d-be8d-a3a27d643de2. Require local_mode true, dialect/class_type sqlite,
active ready bootstrap and exact source before migrations/test writes. Loopback is not
proof of storage locality. No hosted fallback.

```bash
.venv/bin/metatables --local runtime status
.venv/bin/python -m scripts.erp.purchasing.setup_local --source-uid 75b7fd29-3b1f-565d-be8d-a3a27d643de2
.venv/bin/python -m scripts.erp.finance.setup_local --source-uid 75b7fd29-3b1f-565d-be8d-a3a27d643de2
PURCHASING_LOCAL_SOURCE_UID=75b7fd29-3b1f-565d-be8d-a3a27d643de2 .venv/bin/python -m uvicorn api.erp.purchasing.local:create_app --factory --host 127.0.0.1 --port 38741 --no-access-log
```

Base/Catalog must already be installed. Purchasing revision 0001 owns only four tables,
namespace erp-purchasing, provider src.erp.purchasing.migrations:migration, version table
erp_purchasing__alembic_version. Optional Finance revision 0002 adds the nullable named
unique Purchasing source link to its invoice table. Inventory has no DDL change. Preserve
applied revisions; never migrate at startup. Restart local Finance and consumers after
its schema/code upgrade, including Inventory/Projects that lazily construct Finance.

The local launcher reuses SDK sign-in, requires loopback client/host/origin and rejects
caller identity headers. PURCHASING_INVENTORY_ENABLED=false and PURCHASING_FINANCE_ENABLED=false
disable optional integrations. Hosted Teams use PURCHASING_READER/WRITER/MANAGER/ADMIN_TEAM_UIDS;
hosted grants and delegation remain unverified.

Frontend uses /api/purchasing proxy to 38741, VITE_PURCHASING_ENABLED and future approved
VITE_PURCHASING_FASTAPI_RELEASE_UID. It remains inside the single ERP build and /docs/.
After conflicts reload original saved state. After uncertain creation look up request UID;
after receipt/bill uncertainty inspect the original purchase order and linked owner record.
Never replay blindly. Cleanup only named disposable fixture UUIDs.

The workflow example is inert outside .mainsequence/workflows, selective -purchasing tag
and own migration dependency. Finance/Inventory extensions require their separate approved
release order. No pushes, tags, reconciliation or platform deployment before user approval.
