# ERP Base local verification

Date: 17 November 2026. Expansion step 1 only. Status: locally verified;
platform deployment and hosted frontend integration await explicit user approval.

The existing working trees were committed before Base implementation:
API `0925a31`, frontend `4b2fc26`. These commits include the local-first rule
and the platform approval gate. No push or release tag was created.

## Delivery evidence

| Gate | Evidence | Status |
| --- | --- | --- |
| API ADR | [ADR 0001](adr/0001-base-api-foundation.md), written before implementation; no Agent/MCP extension | Done |
| Independent backend | Thirteen Base models, explicit provider, own namespace/version table, Base-only entrypoint and module registration | Done |
| Local migration | Revision `0001` applied through local MetaTables; 14 active bindings including the version table; repeat application preserved data | Done locally |
| Local seed | Explicit stable-ID starter reference set and shared defaults; repeated seed added zero reference records | Done locally |
| Backend tests | `.venv/bin/pytest tests/erp/base -q`: **18 passed**, one upstream Starlette deprecation warning | Passed |
| Static checks | Ruff on Base service, API, migration, scripts, Job, tests and module registry | Passed |
| First API deployment | Loopback Uvicorn `api.erp.base.local:create_app`, port 38651, actual SDK sign-in and local SQLite | Verified locally |
| Companion frontend | Independent app/guide build, actual local API browser flows, six SDK viewports, light/dark presets | Verified locally |
| CRM regression | Existing suite: **365 passed, 58 skipped**; skipped checks remain unverified | Passed with stated skips |
| Platform deployment | No hosted Base migration, resource release, active Base workflow, push or tag | Awaiting approval |
| Hosted frontend integration | Actual Command Center host, workload grants, Teams and production storage engine | Not performed |

## Runtime evidence and test boundary

The verified MetaTables runtime reported `local_mode: true`, `dialect: sqlite`,
active/ready initialization, no source error and local DataSource
`75b7fd29-3b1f-565d-be8d-a3a27d643de2`. Its catalog was initialized through
`0016_table_namespaces`. Base bindings use provider `src.erp.base:erp-base`
and namespace `erp-base`. Routine application access uses the governed
MetaTables SQL API, not a direct SQLite connection.

The previously running local service had stale identity state and returned 503.
It was restarted with the current installed client and existing SDK sign-in;
the existing database was preserved. Pending local catalog initialization was
applied before Base migrations. No remote fallback or fabricated identity was used.

Tests cover migration/seed repetition; ownership and import independence from
CRM; CRUD and fresh-process persistence; strict input schemas; stale updates;
audit atomicity; archive/restore and active-reference guards; country/subdivision
consistency; party kinds; operating-company cycles; private preferences;
permissions; immutable identities and unique codes; decimal rounding; concurrent
different allocation requests; concurrent retries of the same allocation;
loopback identity protection; disabled routes; non-local runtime rejection; and
portable SDK discovery/collection schemas with valid and invalid fixtures.

Service permission tests use explicit fixture actor IDs to test scoping. They
do not claim those fixture actors passed identity middleware. The local HTTP and
browser checks use actual SDK authentication. Python fixtures remove only their
own records; browser fixtures remain archived in the local Base namespace.

The frontend verifies person creation/edit, a stale edit caused by a real
concurrent API update, reload, archive/restore, relationship pickers,
affiliation/company creation, scoped number allocation and currency rounding.
Startup gating and manual retry are checked against a held or failed readiness
response followed by the real API. All actual resource lists return successfully.
The built 12-page guide passes desktop/mobile light/dark checks and Help round-trip.
Its production direct-open view correctly requires Command Center.

## Remaining gates and known limits

SQLite evidence does not establish production-engine concurrency or hosted
authorization. Before proposing platform delivery, validate the exact Base-only
workflow and migration Job, release identity/ownership, Teams, storage grants,
host origin and delegated API binding, and run appropriate production-engine
checks. Obtain explicit user approval before any action that can deploy.
No active Base workflow has been installed; the future migration Job entrypoint
exists but has not been run against the platform.

The starter reference data is intentionally small. The frontend currently uses
English labels and SDK fallback messages; language records do not provide
translations. This release has no hard delete, party merge, CRM extraction,
financial accounting, FX conversion, legal document issuance, new Agents or MCP.
Number-allocation retry is durable in the API; the frontend retains its request
UUID only while that editor remains mounted.

The other session's CRM migration/facade cleanup is separate work. Its edits
are neither rolled back nor included in the Base implementation commits.
Do not start step 2 while Base's hosted completion gates remain open.
