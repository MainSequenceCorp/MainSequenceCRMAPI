# Local delivery and recovery

All mutation verification and the first application run use actual MetaTables
local SQLite. The reviewed source for this delivery is
`75b7fd29-3b1f-565d-be8d-a3a27d643de2`. An address on localhost alone does not prove
local storage. The setup script and wrapper verify runtime local mode, SQLite,
active/ready bootstrap, source availability and the exact expected UUID.

Run from the API repository with its installed environment and existing SDK
sign-in. Ensure the initialized local MetaTables service is available first.

```bash
.venv/bin/python -m scripts.erp.catalog.setup_local --source-uid 75b7fd29-3b1f-565d-be8d-a3a27d643de2
CATALOG_LOCAL_SOURCE_UID=75b7fd29-3b1f-565d-be8d-a3a27d643de2 .venv/bin/python -m uvicorn api.erp.catalog.local:create_app --factory --host 127.0.0.1 --port 38661
```

Setup applies only `src.erp.catalog.migrations:migration`. Revision 0001 creates
the initial schema; 0002 adds categories, purchase units, descriptions, reference
units and rounding increments. Applied files are immutable. 0002 refuses existing
draft unit/item records; investigate and author a reviewed migration/backfill
before proceeding with a populated draft. Do not erase real data to bypass it.
Repeated upgrade at head is safe and does not seed records.

Read `/api/catalog/v1/ready/` on port 38661: expect module catalog, local true,
schema revision 0002 and the exact source UUID. The wrapper binds loopback only,
rejects foreign origins/caller identity headers and injects the actual SDK token.
The hosted entrypoint is `api/erp/catalog/main.py`; never deploy `local.py`.
No application startup migration or hosted fallback exists.

The companion ERP frontend runs on port 5175 and proxies `/api/catalog` to 38661.
Open `/catalog/items`. It uses the one existing Vite app and artifact; there is
no separate Catalog static site. Node 24 is required for frontend builds.
A hosted build needs the approved same-Environment release UUID in
`VITE_CATALOG_FASTAPI_RELEASE_UID`; setting `VITE_CATALOG_ENABLED=false` hides
Catalog. Unbound hosted builds omit Catalog. Backend `create_app(enabled=False)`
omits its business routes while preserving data. The migration job exists as
`jobs/erp/catalog/migrate.py` but is not scheduled or reconciled locally.

## Tests and operational evidence

```bash
CATALOG_LOCAL_SOURCE_UID=75b7fd29-3b1f-565d-be8d-a3a27d643de2 .venv/bin/python -m pytest tests/erp/catalog -q
.venv/bin/python -m mkdocs build --strict -f documentation/catalog/mkdocs.yml
```

Tests verify actual local storage and clean up only their owned fixture UUIDs
through governed MetaTables operations. Browser fixtures remain archived. No
seeded production catalog is implied. The module's `engineering/catalog/`
verification document records outcomes, source identity and limitations.

## Recovery

Readiness failure: inspect the runtime and SDK sign-in, verify the exact source
and migration bindings, then restart the local API. Do not select a hosted source
or run migrations on another source as a fallback. A lost response during upgrade
requires inspecting the provider's current revision/bindings before retrying;
never edit a successfully applied file.

Business-write uncertainty: read the record or unique code before replay. Restore
archived dependencies before dependent records. For migration/data recovery,
preserve the existing database and review a local backup/forward migration.
0002 intentionally refuses automatic downgrade; it would otherwise discard data.
Disabling UI/API is reversible and does not roll back storage.

## Platform release remains gated

The candidate YAML lives outside `.mainsequence/workflows` and is inert. Before
any release, validate it through the target branch's platform validator, review
access to the correct MetaTables Environment and Teams, verify the production
engine, and pin exact tested commits. Obtain user approval before moving it into
active discovery, pushing/tagging, reconciling workflows or running hosted jobs.

The future execution graph prepares Catalog's image, runs Catalog's migration
job from that image, then deploys the API only after success. Both resources
match `^v[0-9]+[.][0-9]+[.][0-9]+-catalog$`. First creation/reconciliation is itself
a deployment-sensitive action, not made safe merely by a tag regex. Existing
CRM broad promotion policies must also be gated before tag isolation is claimed.
The single ERP frontend is released separately after the Catalog binding is
available. Observe real platform run/activation/readiness and frontend behavior;
SQLite and browser success do not prove hosted completion or build savings.
