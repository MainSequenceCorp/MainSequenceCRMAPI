# Manufacturing verification — 17 November 2026

Actual local storage: source 75b7fd29-3b1f-565d-be8d-a3a27d643de2, local_mode true,
SQLite class/dialect, active/ready bootstrap and exact source checked before writes.
Manufacturing revision 0001 freshly installed and repeated successfully. Inventory's
own additive 0002 preserves applied 0001; production location constraint and nullable
batch/source uniqueness are included. All five Manufacturing models belong only to
its metadata, registry and provider. Every column has label/description; two human
search phrases per model rank the intended table first in the actual local catalog.

Seven focused integration tests pass (23.89 seconds). Maximum eight components plus
one output fits the 32-statement transaction limit through reservation, completion
and Finance handoff. Competing reservations have one winner. Late stock and Finance
conflicts roll back every proposed owner change. Exact scaling rejects recurring or
unsupported fractions. Frozen/archived recipe rules, ordered operations, cancellation,
stock-ledger reconciliation, repeated posting denial, independent owner permissions,
disabled Finance and wrong-source checks pass. Fresh-process persistence and absence
of optional Finance imports pass. Actual loopback SDK-authenticated HTTP validates
pinned 0.5.19 collection/discovery contracts; forged caller headers, external origin/
host, boolean versions and unsupported queries fail.

Local deployment: Manufacturing 38751, Inventory 38731 and Purchasing 38741 restarted
to load Inventory 0002. Finance remains 0002. Launchers reuse existing SDK sign-in;
no credentials copied into browser configuration. Required owner readiness passes.
No migration at API startup. No platform migration/deployment/push/tag performed.

Actual browser creates and activates a BOM, saves production, reserves all components,
starts/finishes sequential operations with minutes/evidence, completes the full batch,
posts Finance valuation, follows stock/source links and confirms individual return
controls are absent. Its own transport makes no direct requests to other domains until
navigation. Six SDK viewport layouts and both themes pass, with tablet screenshot
reviewed. Original-UUID lookup recovers a committed uncertain creation with exactly
one POST. Stale draft reload and dirty navigation guards pass. A final rerun passes
after ensuring work-step evidence resets when a record is reloaded. Held/failed first
readiness, Retry, both feature Help links and return-to-application pass.

Three new user guides join all 73 built guides. Shared General → Modules ordering,
Manufacturing after Purchasing and before Settings, all module links, desktop/mobile,
light/dark, footer Documentation, keyboard/new-tab behavior and dirty navigation pass.
Existing ERP submenu/history/mobile checks pass. Nine frontend unit files, TypeScript,
theme audit of eight CSS files, docs validation, combined Vite/Docusaurus build and
strict Manufacturing/Inventory/Purchasing MkDocs builds pass. Ruff and whitespace
checks pass. Full ERP regression: **550 passed, 41 warnings in 230.11 seconds**.

Fixtures use governed owner operations and explicit disposable UUID cleanup, including
Inventory entries/Finance postings before their source records. No user records removed.
Reproduce with MANUFACTURING_LOCAL_SOURCE_UID, INVENTORY_LOCAL_SOURCE_UID and
SALES_LOCAL_SOURCE_UID set to the verified source, then `.venv/bin/python -m pytest
 tests/erp/manufacturing -q`. Full tests/erp uses all module source variables and the
established local PostgreSQL runtime for legacy fixtures; distinguish that compatibility
coverage from the new SQLite integrations. API runner `tests.erp.manufacturing.run_browser
 --frontend <checkout>` owns browser fixtures. Frontend startup and tests/application
suites check gates and shared artifacts. Evidence logs/screenshots: /tmp/manufacturing-*.

Hosted identity/grants/engine/delegation, workflow reconciliation and release selection
remain unverified and await explicit approval. Bounded single-level full-batch scope
and deferred OpenERP capabilities are documented in the source review and ADR.
