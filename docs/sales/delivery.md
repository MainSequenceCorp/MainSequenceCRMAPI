# Local delivery and recovery

Verify actual MetaTables runtime local mode, SQLite, active ready bootstrap and
source `75b7fd29-3b1f-565d-be8d-a3a27d643de2` before any migration or mutation.
Base and Catalog migrations must already be finalized. SDK sign-in is reused;
never print credentials or substitute caller UID headers.

```bash
.venv/bin/python -m scripts.erp.sales.setup_local --source-uid 75b7fd29-3b1f-565d-be8d-a3a27d643de2
SALES_LOCAL_SOURCE_UID=75b7fd29-3b1f-565d-be8d-a3a27d643de2 .venv/bin/python -m uvicorn api.erp.sales.local:create_app --factory --host 127.0.0.1 --port 38671
```

The setup applies only `src.erp.sales.migrations:migration`, revision 0001,
namespace `erp-sales`, version table `erp_sales__alembic_version`. Readiness
`/api/sales/v1/ready/` must identify Sales, local true, revision 0001 and the
expected source, including Base/Catalog source bindings. No startup migration
or hosted fallback is permitted. Applied migration history must remain immutable.
The initial local scaffold revision was formatted after its first application;
DDL was unchanged, and subsequent repeated upgrade/restart checks passed. Future
revisions must be formatted and finalized before application.

Vite 5175 proxies `/api/sales` to 38671 (`SALES_LOCAL_API_ORIGIN` override).
Use `/sales/orders` in the shared ERP app. Optional CRM reads use
`SALES_LOCAL_CRM_ORIGIN`, default loopback port 38641; `SALES_CRM_ENABLED=false`
disables them. Only an exact HTTP loopback origin is accepted. Hosted API entry
point is `api/erp/sales/main.py`; never deploy `local.py`.

Hosted inclusion requires an approved exact same-Environment
`VITE_SALES_FASTAPI_RELEASE_UID`. `VITE_SALES_ENABLED=false` hides the frontend;
`create_app(enabled=False)` omits business routes while preserving storage. The
root frontend remains one static-site resource and artifact.

## Checks

```bash
SALES_LOCAL_SOURCE_UID=75b7fd29-3b1f-565d-be8d-a3a27d643de2 .venv/bin/python -m pytest tests/erp/sales -q
.venv/bin/python -m mkdocs build --strict -f documentation/sales/mkdocs.yml
```

The browser runner `python -m tests.erp.sales.run_browser --frontend <paired-root>`
uses disposable Base/Catalog/Sales fixtures through the verified local client.
Expose Node 24 and installed Playwright through PATH/NODE_PATH. It removes only
its owned UUIDs even on failure. Tests of optional linkage use actual CRM HTTP
reads over owned governed fixtures; they do not exercise legacy CRM board writes.

## Recovery and approval gate

On readiness failure, inspect the local runtime, schema bindings and SDK sign-in.
Preserve the database; do not select a hosted source. After an uncertain upgrade,
inspect current revision/bindings before retrying. Use reviewed backup restoration
or a forward migration for storage recovery; downgrade discards Sales data.
For uncertain business writes, reconcile using the saved/request UUID and version.

`engineering/sales/deployment/sales-api.yaml.example` is an inert planning example,
not platform-validated and outside active workflow discovery. The intended
independent release matches `^v[0-9]+[.][0-9]+[.][0-9]+-sales$`, prepares Sales's
image, runs `jobs/erp/sales/migrate.py`, then activates the API after success.
Base/Catalog availability and permissions are prerequisites, not automatic
redeployments. Before activation, fetch the target branch's current template,
validate exact content, verify access/policies and production-engine behavior,
and obtain explicit user approval. No push, tag, active reconciliation, hosted
migration or platform deployment is authorized. Existing broad CRM promotion
policies must be gated before module tag isolation is claimed.
