# Projects and services local verification

17 November 2026. OpenERP review preceded the API ADR and implementation.
Actual MetaTables runtime: local true, SQLite, bootstrap active/ready, exact source
`75b7fd29-3b1f-565d-be8d-a3a27d643de2`. Runtime/source is rechecked before mutations.
No hosted fallback or application database engine was introduced.

## Ownership, migrations and API

Four Projects-owned tables, namespace `erp-projects`, own provider and version table,
revision 0001. Official scaffold/revision were reviewed and formatted before applying;
only Projects DDL is present. Repeated upgrade preserves Base/CRM/Catalog/Sales/Finance
revision bindings. Fresh-process reads retain a project; core API imports no CRM,
Catalog, Sales or Finance package. Base is required; commercial adapters are lazy.

Local API runs on 38691, with Vite's independent `/api/projects` transport. Actual
SDK sign-in is used. Forged identity and foreign origins are rejected. No startup
migration is allowed. The inactive example selects only `-projects` tags and runs
the Projects migration before API activation; it is not platform-validated/approved.

Initial focused Projects/Finance tests: 18 passed. They exercise independent
project/task/effort operation, reversal, completion and freeze, version races between
new work and delivery, assignment/date/permission validation, atomic audit rollback,
source-order duplication, same-source billing rollback and trace, migration isolation,
restart and actual authenticated SDK collection/discovery contracts.

Browser verification found the missing Base public person filter; the owner service
and HTTP API now filter before pagination/count, with tests and Base ADR/contract
notes. Billing input now validates tax and date ordering before a handoff, including
the Finance source-invoice API. No schema changes were needed for these adaptations.

## Frontend and guide evidence

Real local browser tests pass project creation, assignment, task editing, stale
conflict/reload, effort recording/void reason/history, dirty draft guards, delivery
freeze and closure, confirmed service order → delivery task → draft Finance invoice
and opening that invoice. Projects browser calls to CRM/Sales/Catalog/Finance were
blocked until deliberate cross-module navigation, confirming independent transport.
Six SDK viewports in both themes pass; narrow screenshot was visually inspected.

An extended run commits a real project then deliberately drops its response.
**Check saved record** finds the original UUID with exactly one mutation. Fixtures
are owned local UUIDs and are removed even after failure. Held/failed readiness with
explicit Retry passes. Existing CRM/Directory/Settings navigation/history passes.

Nine frontend unit files, TypeScript, combined Vite/Docusaurus build, theme audit,
documentation validation, all 53 guides on desktop/mobile and light/dark, shared
General/Modules ordering, links and keyboard/unsaved-draft protection pass.
Strict Projects and CRM backend MkDocs builds pass. Build emits pre-existing chunk
size and update-check notices; these are not failures.

## Regression investigation

An initial complete suite passed 509 tests. After adding Base/filter/date checks,
511 passed and one existing CRM note timestamp equality check failed intermittently.
The issue was reproduced deterministically using an owned PostgreSQL fixture date
with trailing fractional zeros. CRM collections validated but discarded Pydantic's
normalized value, unlike details. Returning that normalized value fixes the source
of the inconsistency without changing storage or command behavior. Relevant CRM
concept/API/delivery docs accompany the repair. The final complete ERP suite passed **512 tests** (41 existing deprecation warnings,
122.24 seconds), including that deterministic regression. An isolated prior pass
was not treated as evidence that the flaky check was fixed.

## Reproduction and remaining gates

Follow `docs/projects/delivery.md`. Set PROJECTS_LOCAL_SOURCE_UID,
FINANCE_LOCAL_SOURCE_UID and SALES_LOCAL_SOURCE_UID to the exact source above.
Run the focused suite or the full `python -m pytest tests/erp -q`; full regression
also needs CATALOG_LOCAL_SOURCE_UID and the existing local PostgreSQL test binaries
and libraries for older CRM compatibility fixtures. New Projects writes use actual
MetaTables Local SQLite. The browser runner is
`python -m tests.erp.projects.run_browser --frontend <paired-root>` with Node 24
and Playwright available. The frontend evidence index lists other commands.

This is bounded fixed-price service delivery, not full OpenERP Projects parity.
Configurable boards, recurring/subtasks, templates, portals, employee-rate billing,
time-derived invoicing and partial/milestone invoices are deferred in the mapping.
CRM's older board/deal-write PostgreSQL-specific SQL remains outside this module.
SQLite evidence does not establish production-engine concurrency. Hosted Teams,
workload grants, namespace ownership, release bindings and activation remain open.
No push, release tag, active workflow, hosted migration or platform deployment.
