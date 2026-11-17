# Sales local verification

17 November 2026. Source review and API ADR preceded implementation.

## Runtime and migrations

Actual MetaTables runtime reports local mode true, SQLite, active/ready bootstrap,
no pending runtime migrations, source AVAILABLE/read-write and exact UID
`75b7fd29-3b1f-565d-be8d-a3a27d643de2`. Installed SDK authentication is used by all
local APIs. No client-owned database engine or hosted fallback was introduced.
Search of existing local MetaTables found CRM opportunities and financial execution
orders, but no existing customer quotation/order storage suitable for Sales.

Only provider `src.erp.sales.migrations:migration` creates Sales's three tables and
version table in namespace `erp-sales`, revision 0001. Repeated upgrades preserve
Base, Catalog and CRM version bindings. Fresh-process reads retain a saved order.
Disabled API creation omits Sales business routes without deleting data, and core
Sales imports no CRM domain package. One formatting-only pass occurred after first
local application of the scaffold revision; no DDL changed. Applied files are now
frozen; finalize formatting before applying future revisions.

Actual local API and proxied readiness identify Sales, local true, revision 0001,
the expected source and matching Base/Catalog dependencies. API runs on 38671;
Vite 5175 includes Sales alongside the existing modules. No workflow was activated.

## Executed checks

- Focused `tests/erp/sales`: **13 passed** in 16.53 seconds before final test-only
  isolation refinement. Actual governed storage, Decimal amounts, strict inputs,
  missing/expired lines, unsaleable references, reader denial, lifecycle and
  immutable terms, duplicate references, concurrent edits, atomic audit rollback,
  downstream cancellation guard, migration isolation and fresh-process reads.
- Actual SDK-authenticated HTTP collection/discovery validated against the pinned
  Command Center schemas; forged identity/foreign origins rejected.
- Optional CRM link uses an actual locally adopted company and actual CRM HTTP
  detail/collection reads. Active Base consumer claims establish customer matching;
  mismatch, archived opportunity and disabled CRM are rejected. Unlinked orders
  work with CRM disabled. Fixture pipeline/stage/deal are inserted through governed
  local statements, then removed by owned UUID; this is read-link integration
  evidence, not CRM board/deal-write portability evidence.
- Ruff on Sales service/API/scripts/job/tests passes. Independent MkDocs strict
  build at `documentation/sales/mkdocs.yml` passes.
- Frontend nine unit files, TypeScript, Vite/Docusaurus combined build, theme audit
  and all 47 guide pages validate. Shared General/Modules sidebar and cross-module
  links pass in the built artifact on desktop/mobile and both themes.
- Real browser save, exact discount amount, dirty guard, concurrent conflict/reload,
  quoted/reopen/confirm/cancel, immutable confirmation and six SDK viewports in both
  themes pass. A real committed POST with its response deliberately dropped is
  recovered by GET of the same UUID with no mutation replay. Fixture cleanup removes
  only owned Base/Catalog/Sales records. Held/failed readiness stimuli and explicit
  Retry pass; existing CRM/Directory/Settings navigation/history/mobile checks pass.

Full ERP regression initially reported 490 passed and one failure due to a mocked
CRM registry cached by an earlier test. Sales's integration fixture now clears that
cache and verifies the exact source before any CRM setup. The identified failed-run
fixture was removed after checking its UUID/name/time and absence of related deals.
Final complete-suite result: **491 passed**, no skips, 41 existing deprecation
warnings, in 95.95 seconds. This includes the corrected Sales integration fixture.

## Reproduction

Follow `docs/sales/delivery.md` for exact local setup and focused tests. Full
regression uses `.venv/bin/python -m pytest tests/erp -q`, both Sales/Catalog local
source variables, and the existing disposable PostgreSQL test binaries on PATH
(with their library directory on LD_LIBRARY_PATH). These existing CRM compatibility
fixtures are local only; new Sales mutation tests use actual MetaTables SQLite.

The paired frontend business browser runner is
`python -m tests.erp.sales.run_browser --frontend <paired-root>` with Node 24 and
Playwright available. The frontend evidence index lists the remaining commands.

## Limits and release gates

Source inspection is not an executed Odoo parity test. Snapshot reads across
owners are not a distributed transaction. SQLite evidence does not establish
production-engine locking. The current CRM board/deal-write paths still contain
PostgreSQL-specific SQL and are outside this Sales read integration; that limit was
observed when initially preparing the optional-link fixture and remains recorded.
Hosted CRM transport, Teams/workload grants, exact binding, production-engine
checks, target-branch workflow validation and platform activation remain open.
The release planning example stays outside discovery; no push, tag, active
reconciliation, hosted migration or deployment was performed.
