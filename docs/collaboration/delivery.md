# Local delivery and recovery

Run from the API repository's installed environment. First inspect actual runtime:

```bash
.venv/bin/metatables --local runtime status
.venv/bin/python -m scripts.erp.collaboration.setup_local --source-uid 75b7fd29-3b1f-565d-be8d-a3a27d643de2
COLLABORATION_LOCAL_SOURCE_UID=75b7fd29-3b1f-565d-be8d-a3a27d643de2 .venv/bin/python -m uvicorn api.erp.collaboration.local:create_app --factory --host 127.0.0.1 --port 38711 --no-access-log
```

Require local_mode true, SQLite, active/ready bootstrap and the exact source before
writes. Setup applies only `src.erp.collaboration.migrations:migration`, namespace
`erp-collaboration`, revision `0001`, version table `erp_collaboration__alembic_version`,
identifier `erp_collaboration.alembic_version`. Its own four tables are registered
explicitly. Applied revision files are immutable. API startup never auto-migrates.

Standalone Collaboration has no business prerequisite. Set
`COLLABORATION_PROJECTS_ENABLED=false` when Projects is absent. Optional linked
work requires an already migrated Projects API/public service at the same local
source. API readiness checks own bindings; integration availability is distinct
from independently verified owner readiness.

Vite `/api/collaboration` proxies loopback 38711. One ERP artifact contains all
module screens and `/docs/` guides. Frontend environment controls are
`VITE_COLLABORATION_ENABLED` and `VITE_COLLABORATION_FASTAPI_RELEASE_UID` for a future
approved hosted API. Existing CRM/static-site resource identities are unchanged.

On failure stop writes, verify runtime/source/provider, and restart the local API.
Do not change the source or fall back to hosted discovery. Reconcile uncertain
creates/posts by the original request UUID. Reload saved records after version
conflicts; never repeat a POST blindly. Fixture cleanup deletes only owned UUIDs.

The `.example` workflow in engineering is inactive: own migration Job precedes
API, both use only the `-collaboration` release-tag regex. Validation/reconciliation,
release tags, pushes, hosted schema changes and hosted integration remain pending
explicit user approval. SQLite evidence does not establish production-engine behavior.
