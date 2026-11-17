# Projects local deployment

Before writes, verify actual MetaTables runtime local true, SQLite, bootstrap
ready/active and source `75b7fd29-3b1f-565d-be8d-a3a27d643de2`.

```bash
.venv/bin/python -m scripts.erp.projects.setup_local --source-uid 75b7fd29-3b1f-565d-be8d-a3a27d643de2
PROJECTS_LOCAL_SOURCE_UID=75b7fd29-3b1f-565d-be8d-a3a27d643de2 .venv/bin/python -m uvicorn api.erp.projects.local:create_app --factory --host 127.0.0.1 --port 38691
```

Revision 0001 was generated with the official provider scaffold, reviewed and
formatted before application; it creates only four Projects tables plus its own
version table. Applied revisions are immutable. Base must already be available.
Sales/Catalog and Finance are required only for their selected integration.
PROJECTS_SALES_ENABLED=false and PROJECTS_FINANCE_ENABLED=false disable optional
adapters. There is no startup migration. The local wrapper refuses foreign origins,
forged identity and a mismatching source. Hosted entrypoint is main.py, never local.py.

Initial focused Projects/Finance tests pass: 18 scenarios. Run with exact
PROJECTS_LOCAL_SOURCE_UID, FINANCE_LOCAL_SOURCE_UID and SALES_LOCAL_SOURCE_UID:

```bash
.venv/bin/python -m pytest tests/erp/projects tests/erp/finance -q
```

Tests use owned governed local fixtures and cleanup by UUID. Browser and final
regression evidence must be completed before this stage is closed. Recovery means
inspect migration bindings/revision before retrying, preserve data and use approved
forward migration or backup restore; never stamp past failure. Business uncertainty
requires read/reconciliation. Disablement preserves storage.

The inactive `engineering/projects/deployment/projects-api.yaml.example` uses only
`-projects` tags and the module's migration job before its API. Target validation,
namespace/workload grants, production-engine checks and hosted transport remain
open. No push, active workflow, tag, hosted migration or deployment is authorized.
