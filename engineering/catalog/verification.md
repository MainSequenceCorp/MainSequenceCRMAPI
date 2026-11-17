# Catalog local verification

17 November 2026. Step 3 only. Local implementation and integration verified;
platform deployment and hosted acceptance remain unapproved and unperformed.

## Runtime and schema evidence

Actual MetaTables runtime: `local_mode: true`, `dialect: sqlite`, source class
SQLite, active/ready bootstrap, no source error, DataSource
`75b7fd29-3b1f-565d-be8d-a3a27d643de2`. Every Catalog mutation test verifies this
identity first. Versions: Python 3.13, Main Sequence 9.0.40,
mainsequence-metatable 0.1.67, FastAPI 0.141.1, MkDocs 1.6.1.

Catalog owns six bindings including its version table, namespace `erp-catalog`,
provider key `src.erp.catalog:erp-catalog`, and revisions 0001 → 0002. No Base/CRM
migration was added or changed. The final binding/restart test uses both real
Base and CRM version identifiers when present and verifies that repeating Catalog
upgrade preserves them. A subprocess imports and uses Catalog without loading
Base or CRM and confirms disabled Catalog routes are absent.

Revision 0001 was applied while drafting the initial schema. Detailed source
review then required 0002. The installed autogenerator's baseline visibility guard
reported only the newly added category table as missing, although governed reads
proved the prior 0001 tables/bindings existed and draft Unit/Item counts were zero.
Used the official `revision --no-autogenerate --rev-id 0002` path, authored the
additive operations explicitly, and applied/repeated the reviewed migration.
This records a client generator limitation; no SDK modification or database
bypass was used. Both applied revision files remain immutable. Their SHA-256 hashes are
`7c178ee36964990aff3521f0d93c12300d54eadedc5c034a1ce9898ee50fe43f` (0001)
and `79a4add9e7430e8b187616575996526aca44787f7ed04d39d14aad1ed3ce0900` (0002). 0002 refuses a
populated draft and automatic downgrade, as documented in the ADR/delivery guide.

The first Catalog application runs at 127.0.0.1:38661 using
`api.erp.catalog.local:create_app` with the exact source environment variable.
Direct and Vite-proxied readiness return 200, local true, schema 0002, the expected
source and signed-in user's capabilities. Application access uses governed
MetaTables operations; no application-owned database engine was introduced.

## Executed backend checks

| Check | Actual result |
| --- | --- |
| `.venv/bin/python -m pytest tests/erp/catalog -q` with explicit local source | Initial 25 passed; final run after correcting the CRM identifier and adding the 16/17-level category boundary: **26 passed** in 12.22 s. |
| `.venv/bin/python -m pytest tests/erp -q` with local source and disposable local PostgreSQL test binaries on PATH | **477 passed**, no skips, in 80.73 s, before those final test-only refinements. Existing local CRM compatibility tests use their own disposable test runtime; this is not Catalog production-engine evidence. |
| Focused corrected migration/restart isolation check | **1 passed**, then included again in the final Catalog suite. |
| Ruff on Catalog service/API/models/migrations/scripts/job/tests and module registry | Passed. |
| MkDocs strict build using `documentation/catalog/mkdocs.yml` | Passed; module-owned API guide generated separately from CRM docs. |

The final Catalog suite covers actual local CRUD, version/uniqueness conflicts,
reader/writer permission boundaries, atomic audit rollback, immutable quantity
semantics, same-group purchase units, category cycles/leaf moves/depth bounds,
archive/restore dependency order, reference uniqueness and first-reference rules,
positive/negative/tie/zero/exact rounding, conversion incompatibility, two competing
writers, strict decimal validation, SDK collection/discovery JSON schemas and
actual SDK-authenticated HTTP requests. Local wrapper tests reject injected
identity and foreign origins. Wrong-runtime rejection is a separately mocked
unit check; it is not represented as live hosted verification.

Python fixtures clean up only their owned UUIDs through governed deletes. Browser
fixtures were created with actual local API calls and then archived in dependency
order: one group, two units, one category and one service. No active fixture
catalog or production seed is claimed. Service capability fixtures exercise
policy directly; only HTTP/browser cases establish real SDK identity integration.
Warnings are existing Starlette/FastAPI deprecations, not failed checks.

## Frontend evidence

Companion frontend uses Node 24, Command Center SDK 0.5.19 and the existing single
ERP Vite root. Nine existing frontend test files pass. Typecheck and combined
`npm run build` pass, including all 27 CRM, 12 Directory and 5 Catalog guide pages.
Documentation validation and SDK theme audit pass.

Real browser checks create group/reference/alternate unit/category/service,
convert two dozen to 24.00, reject dirty navigation until explicit discard, trigger
a stale edit through a real competing API write, reload, archive and restore.
Catalog loads with both CRM and Base requests blocked and makes zero requests to
those APIs. Ordinary menu expansion preserves the current route. Six SDK viewports
pass layout/shell checks with light/dark themes and actual mobile pointer settings.
All five built Catalog guide pages pass mobile/desktop and light/dark overflow/
console/network checks, Help round-trip and the production direct-open host gate.
Held/failed readiness responses verify startup gating and explicit retry against
the real API; those failure stimuli are mocked transport responses. Existing
CRM/Directory/Administration navigation, history, reload and mobile checks pass.

Reproducible browser commands and frontend ownership are in the companion module
index. This verifies SDK layout contracts and the exercised interactions; it is
not a claim of a complete accessibility audit or hosted Command Center acceptance.

## Remaining release gates

No active Catalog workflow, release, hosted migration, new Agent/MCP, tag or push
was created. The YAML candidate is review material outside active discovery, not
a platform-validated declaration. Production database behavior, hosted Teams and
workload grants, same-Environment delegated binding, tag isolation, actual image
build selection, migration failure gating and hosted frontend behavior remain
unverified. Existing broad CRM deployment policy must be addressed before claiming
module-selective releases. Obtain explicit user approval before deployment actions.
