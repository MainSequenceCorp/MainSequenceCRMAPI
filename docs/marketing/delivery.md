# Local setup and recovery

Verify actual MetaTables Local mode, SQLite, active ready bootstrap and source
`75b7fd29-3b1f-565d-be8d-a3a27d643de2` before any write. Base must already be installed.

```bash
.venv/bin/metatables --local runtime status
.venv/bin/python -m scripts.erp.marketing.setup_local --source-uid 75b7fd29-3b1f-565d-be8d-a3a27d643de2
MARKETING_LOCAL_SOURCE_UID=75b7fd29-3b1f-565d-be8d-a3a27d643de2 .venv/bin/python -m uvicorn api.erp.marketing.local:create_app --factory --host 127.0.0.1 --port 38721 --no-access-log
```

Own provider `src.erp.marketing.migrations:migration`, namespace `erp-marketing`,
revision 0001, version table `erp_marketing__alembic_version`, identifier
`erp_marketing.alembic_version`. Five explicit owned models; no foreign-table DDL.
Startup does not migrate. Applied revisions are immutable.

Local launcher uses actual SDK authentication, rejects supplied caller identity
headers and non-loopback host/origin. Source mismatch aborts before writes. Optional
CRM reads use local port 38641 and the existing SDK-authenticated local API; set
`MARKETING_CRM_ENABLED=false` to disable. Only exact loopback origins are accepted;
no hosted credentials or guessed URLs are forwarded.

Frontend Vite proxies `/api/marketing` to 38721. Controls are `VITE_MARKETING_ENABLED`
and future `VITE_MARKETING_FASTAPI_RELEASE_UID`. All screens and guides share the one
ERP static artifact. Capture and simulation are unavailable outside verified local
mode; no outbound sender or provider is configured by this release.

After errors, stop writes, check runtime/provider/source, then restart locally.
Read original UUID after uncertain creation/addition; reload saved results after
uncertain capture or simulation. Process only remaining pending recipients; never
blindly replay a command. Keep fixture cleanup to owned UUIDs. Do not change the
active source during work or fall back to hosted discovery.

The engineering `.example` workflow is inactive and unvalidated on the platform.
It proposes only an own migration Job and API with the `-marketing` release-tag
pattern. Hosted migrations/deployments, pushes/tags/reconciliation and any external
message transport require explicit user approval after local verification. SQLite
checks do not establish production-engine behavior or real email deliverability.
