# Local operations

Before writes confirm MetaTables local_mode=true, SQLite dialect/class_type, active and
ready bootstrap and exact DataSource 75b7fd29-3b1f-565d-be8d-a3a27d643de2. A loopback URL
alone proves none of these. No fallback to hosted discovery. Keep the SDK user signed in.

```sh
.venv/bin/python -m scripts.erp.reporting.setup_local --source-uid 75b7fd29-3b1f-565d-be8d-a3a27d643de2
REPORTING_LOCAL_SOURCE_UID=75b7fd29-3b1f-565d-be8d-a3a27d643de2 .venv/bin/uvicorn api.erp.reporting.local:create_app --factory --host 127.0.0.1 --port 38771 --no-access-log
```

Provider src.erp.reporting.migrations:migration registers five owned tables. Revision 0001
and version table erp_reporting__alembic_version are independent; repeated upgrade is safe.
Never edit applied revisions. Source modules need their own verified schemas before capture,
but Reporting imports none at startup and has no mandatory source prerequisite. Configure
source enable flags and verify each owner's own read permissions. No migrations on API start.

```sh
.venv/bin/python -m scripts.erp.reporting.worker_local --source-uid 75b7fd29-3b1f-565d-be8d-a3a27d643de2 --port 38771 --poll-seconds 5
```

Run the worker as a separate foreground process; --once checks one tick. It verifies the
runtime before every request and sends no injected identity. The API verifies SDK sign-in.
A stopped worker leaves schedules due without executing them; restart processes one bounded
step per tick. Current-user schedules only. API heartbeat becomes unavailable after 30s or
restart. Stop the worker during deterministic integration tests. Local worker availability
does not establish hosted durability. No autostart service or platform scheduler is installed.

Frontend Vite 5175 proxies /api/reporting to 38771. One combined build contains all ERP
screens and /docs/. VITE_REPORTING_ENABLED controls local module composition; non-local
frontend requires VITE_REPORTING_FASTAPI_RELEASE_UID and approved delegated access.
Hosted roles use REPORTING_{READER,WRITER,MANAGER,ADMIN}_TEAM_UIDS; creator privacy remains.

Inspect run detail after uncertain actions. Use original request UID for uncertain creation.
Resolve source failure, retry explicitly, then continue. Recover an expired interrupted
claim; cancellation invalidates old worker output. Completed sources survive recovery.
Pause schedules before maintenance; cancel queued work separately. Restore API/worker and
verify readiness/progress. Never delete user records or silently change source scope.

Focused tests: set REPORTING_LOCAL_SOURCE_UID and supporting SALES/COMMERCE/FINANCE/
INVENTORY/PURCHASING/MANUFACTURING/PROJECTS local source variables to the exact verified UID,
then run .venv/bin/python -m pytest tests/erp/reporting -q. Browser runner:
.venv/bin/python -m tests.erp.reporting.run_browser --frontend <paired-frontend-checkout>.
Use Node 24 and bundled Playwright/Chrome. Exact disposable fixtures are owner-cleaned.

The inert engineering/reporting/deployment/reporting-api.yaml.example uses a module tag
v<major>.<minor>.<patch>-reporting and own migration job before API. It is outside active
workflow discovery. No hosted worker declaration is implied. Platform workflow validation,
tag selection, production engine, delegated identity and actual deployment require explicit
user approval. No push, tag, activation, hosted migration or platform deployment was made.
