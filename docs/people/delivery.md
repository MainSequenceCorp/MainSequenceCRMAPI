# Local People delivery

Use the existing API Python environment and SDK sign-in. First inspect actual runtime
status: local mode true, dialect SQLite, SQLite source class, bootstrap active/ready,
no data-source error and expected source
`75b7fd29-3b1f-565d-be8d-a3a27d643de2`. Never infer this from loopback or fall back to hosted.
Base must already be locally migrated and ready. Projects is optional.

```bash
.venv/bin/python -m scripts.erp.people.setup_local --source-uid 75b7fd29-3b1f-565d-be8d-a3a27d643de2
PEOPLE_LOCAL_SOURCE_UID=75b7fd29-3b1f-565d-be8d-a3a27d643de2 .venv/bin/python -m uvicorn api.erp.people.local:create_app --factory --host 127.0.0.1 --port 38701
```

People owns provider `src.erp.people.migrations:migration`, namespace `erp-people`,
version table `erp_people__alembic_version`, revision 0001 and four owned tables.
The official scaffold's version identifier is `src.erp.people.alembic_version`.
Applied revisions are immutable. Setup verifies exact source before upgrading; API
startup only resolves active catalog bindings. Repeated upgrade/restart must retain
records and leave other providers unchanged. No direct application database connection.

The companion frontend proxies `/api/people` to 38701 in the shared Vite site.
`VITE_PEOPLE_ENABLED=false` omits its navigation; an unbound hosted build also omits
it. Future binding uses `VITE_PEOPLE_FASTAPI_RELEASE_UID`. API factory `enabled=False`
removes business routes; disablement does not delete data. `PEOPLE_PROJECTS_ENABLED=false`
disables staffing references/commands, leaving independent workforce operations.

Run with exact PEOPLE_LOCAL_SOURCE_UID and PROJECTS_LOCAL_SOURCE_UID for optional
staffing fixtures:

```bash
.venv/bin/python -m pytest tests/erp/people -q
.venv/bin/python -m tests.erp.people.run_browser --frontend <paired-frontend-root>
.venv/bin/mkdocs build --strict -f documentation/people/mkdocs.yml
```

Browser runner needs Node 24, Playwright and installed Chrome. It owns UUID-scoped
fixtures and deletes only those records after verification. A distinct policy fixture
actor creates the other-person absence; browser approval itself uses actual SDK
sign-in. Policy fixture actors are not claimed as separately authenticated accounts.
Complete ERP regression also supplies Catalog/Sales/Finance/Projects source variables
and local PostgreSQL fixture binaries for older CRM compatibility tests. New module
writes always use MetaTables Local SQLite. See engineering evidence for actual results.

On connection loss, check readiness then original UUID/current versions; do not replay
an uncertain write. A confirmed committed creation is opened, not duplicated. On a
stale employee/request/task, reload every affected aggregate before issuing a new
intent. Fix a failed migration from actual physical/catalog state; no destructive
catalog deletion, stamping or automatic downgrade. Stop the local process before
changing source identity and rerun the guarded launcher.

`engineering/people/deployment/people-api.yaml.example` is an inactive candidate with
only `-people` release tags and `jobs/erp/people/migrate.py` before API activation.
It is outside active workflows and unvalidated on the platform. Future hosted delivery
requires an owning Team/namespace, workload membership, all cross-owner grants and
People Team configuration (PEOPLE_READER/WRITER/MANAGER/ADMIN_TEAM_UIDS), independent
Base/Projects authorization, production-engine evidence, release binding and explicit
user approval. No push, tag, hosted migration or reconciliation is authorized.
