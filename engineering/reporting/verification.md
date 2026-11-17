# Reporting and automation verification — 17 November 2026

Selected local cycle complete. Supplied OpenERP source review and API ADR precede the
implementation. This is the bounded adaptation in openerp-coverage.md, not full parity.

Storage: actual MetaTables Local SQLite source 75b7fd29-3b1f-565d-be8d-a3a27d643de2,
verified local_mode, SQLite dialect/class, active/ready bootstrap and exact UID before
writes. Five independent models, own metadata/provider/version table. Reviewed initial
revision 0001 affects only owned Reporting tables/FKs/constraints; freshly applied and
repeat upgrade verified. Applied migration remains unchanged. All columns have authored
labels/descriptions. Ten human searches in the actual local catalog discover the intended
models: nine rank first; the broader execution/lease query ranks Run second, tied with a
CRM transfer history result. No claim that similarly named execution stores are interchangeable.

Seven focused integration tests pass (26.33 seconds):

- Exact company/currency reconciliation, source links, immutable completed results,
  live source-version change detection, CSV prefix protection and large Decimal amounts.
- Creator privacy, role/source permissions, permission revocation, disabled optional
  owners, same-source checks, frozen configuration and strict schema validation.
- Competing claims, one winner, cancellation fence, expiry, stale worker denial and recovery.
- Safe source errors, explicit retries retaining completed sources, 200-record failure
  boundary, incomplete-result denial and source count consistency.
- Competing due schedulers, deterministic one-run creation, no overlap, pause/archive
  behavior and late-statement failure rolling back schedule/run/steps together.
- Real Projects, Inventory, Purchasing and Manufacturing records captured through owner
  read ports, with status counts and source identity; no owner mutation by Reporting.
- Actual installed-SDK HTTP identity, discovery/collection contracts pinned to 0.5.19,
  forged identity/origin denial, strict queries, worker status/tick, fresh-process source
  import isolation, disabled module routes and repeated own migrations.

Full ERP regression: **564 passed, 41 warnings in 279.80 seconds**, one uninterrupted
run. Warnings are existing dependency/deprecation notices. New domain integrations use
actual SQLite; established legacy ERP fixtures also exercise local PostgreSQL. This
local evidence does not establish production-engine or hosted delegation behavior.

Local first deployment: Reporting API 38771, own readiness and schema revision 0001,
Vite 5175 proxy, same ERP artifact. Worker script launched as a separate process during
the real browser flow; it called the authenticated loopback API as the verified SDK user,
queued a due schedule, completed two source steps and reported running → succeeded → idle.
UI heartbeat and latest-run navigation passed; pause stopped future scheduling. Browser
worker stopped before fixture cleanup. No in-API timer/migration or platform scheduler.
A separate local worker was left running for local use after deterministic tests; its
actual recent heartbeat was verified. Final readiness checks returned HTTP 200 for CRM
and all thirteen independent expansion APIs.

Companion browser checks passed: definition creation, manual commercial capture, exact
25 net / 30 gross / 30 allocated / 0 remaining fixture, CSV download, current-version
check, original owner record navigation via result rows and invoice links, real persisted
failure retry and expired-claim recovery. Lost responses after real transactions resolved
through the original UUID with exactly one POST for create and queue. Cancellation,
stale edit/reload, dirty navigation and independent module transport passed. Six SDK
viewports and both themes passed; tablet/mobile screenshots were inspected. No real
payment or outbound message was executed; source fixtures record observed transactions.

Held/failed first readiness, explicit Retry, three feature Help links and return navigation
passed. All **82 built guides** passed desktop/mobile and both themes with one shared
General → Overview / Modules sidebar; Reporting follows Commerce, Settings remains last.
Help landing now lists every module in that order. Footer Documentation, module links,
keyboard/new-tab and unsaved forms passed. Existing ERP submenus/history/reload/mobile
checks passed. Nine frontend unit files, TypeScript, ten-file theme audit, docs checks,
combined application/docs build, strict Reporting MkDocs and Ruff pass. Maintained-source
whitespace checks pass; the generated, already-applied 0001 migration retains its empty
Revises header trailing space instead of changing an applied revision.

Reproduce using docs/reporting/delivery.md. Logs/screenshots are local /tmp/reporting-*;
full command environment additionally includes the established legacy local PostgreSQL
binaries/libraries. Browser runner is tests.erp.reporting.run_browser; it tracks exact
UUIDs, stops its worker before deleting fixture children and then unwinds business owners.
No user records removed. Data/claims survive process boundaries and owner outputs remain
immutable after success. Capture is explicitly a rolling window, not atomic across owners.

Platform gate remains open: hosted identity/engine/delegation, worker execution identity,
workflow validation, module-tag selection and actual deployment are unverified. Inert
workflow candidate is outside active discovery. No push, tag, hosted migration, workflow
activation or platform deployment was performed. Explicit approval is required first.

Implementation revisions: API `3a30fb3`; companion frontend `38ad588`. The latter also
records the completed 14-stage local expansion plan and shared 82-guide navigation.
These are local Git commits only; schema revision remains Reporting 0001. A subsequent
documentation-only commit records this pairing without changing either runtime artifact.
