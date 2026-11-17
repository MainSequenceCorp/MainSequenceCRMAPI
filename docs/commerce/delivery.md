# Local deployment and recovery

Verify MetaTables local_mode true, SQLite dialect/class_type, active/ready bootstrap
and exact source 75b7fd29-3b1f-565d-be8d-a3a27d643de2 before writes. Loopback is not proof.

```bash
.venv/bin/metatables --local runtime status
.venv/bin/python -m scripts.erp.commerce.setup_local --source-uid 75b7fd29-3b1f-565d-be8d-a3a27d643de2
COMMERCE_LOCAL_SOURCE_UID=75b7fd29-3b1f-565d-be8d-a3a27d643de2 .venv/bin/python -m uvicorn api.erp.commerce.local:create_app --factory --host 127.0.0.1 --port 38761 --no-access-log
```

Base/Catalog are prerequisites. Sales and Finance remain lazily optional; set
COMMERCE_SALES_ENABLED=false or COMMERCE_FINANCE_ENABLED=false to disable. Commerce
provider src.erp.commerce.migrations:migration owns only its five models and version
table erp_commerce__alembic_version. Applied revision 0001 remains unchanged. Sales
adds its own public complete checkout plan without DDL. Never migrate at API startup.

Build the paired frontend with npm run build. Start a separate local customer process
using the same source variable plus COMMERCE_PUBLIC_FRONTEND_DIST=<absolute frontend>/dist:
`.venv/bin/python -m uvicorn api.erp.commerce.public_local:create_app --factory --host
127.0.0.1 --port 38762 --no-access-log`. Visit /shop/<published-slug> on 38762. It serves
the same built ERP artifact, without the trusted merchant Vite proxy. No second Static
Site/build is introduced. SDK sign-in is verified server-side; no credentials in browser
configuration. The preview rejects external host/client/origin and forged caller headers.

Merchant Vite proxy /api/commerce points to 38761; VITE_COMMERCE_ENABLED controls inclusion.
COMMERCE_READER/WRITER/MANAGER/ADMIN_TEAM_UIDS configure future hosted role mappings.
Hosted release UID and public ingress/service identity require an approved deployment
design. The inert -commerce workflow covers private API plus own migration Job only.
It remains outside active workflows. No push/tag/reconciliation/hosted migration or
platform deployment without explicit user approval.

On stale records reload; on uncertain create inspect original UUID before retry. Revoke
exposed portal access and issue a new grant; no secret retrieval exists. Expired/revoked
codes fail server checks. Fixture cleanup removes only explicitly owned UUIDs, Finance
children before invoices and Commerce children before sites/Sales prerequisites.
