# Inventory local verification — 17 November 2026

Local cycle verified; hosted release remains unapproved. Source review and API ADR
preceded development. The selected Finance extension has its own API ADR and docs.

## Persistence and backend evidence

Actual MetaTables Local mode, SQLite, active/ready bootstrap and exact source
75b7fd29-3b1f-565d-be8d-a3a27d643de2 were checked before revision authoring, upgrade
and fixture writes. Own six-model provider applied reviewed revision 0001 in namespace
erp-inventory, with own version table erp_inventory__alembic_version. Repeated upgrade,
independent API imports, wrong-source refusal and fresh-process persisted reads pass.
Applied revisions remain immutable. Finance only refreshed Posting descriptions
through its own existing provider; no foreign DDL or new Finance revision was needed.

Six focused acceptance tests passed (17.99s); full ERP regression **536 passed**, 41
existing warnings, 190.06s. A final focused run after the additive stock-unit display
field passed all six (17.85s). Existing CRM regressions use established local PostgreSQL
compatibility fixtures; every new Inventory migration/mutation uses actual Local SQLite
through MetaTables. Policy-only actors are distinguished from actual SDK-authenticated
HTTP. All successful and failed-run disposable records were cleaned by exact owned
UUIDs; two early fixture cleanup mistakes were corrected and their remaining references
removed using recorded IDs/times and a saved browser fixture manifest.

Scenarios cover receipt/transfer/delivery/return reconciliation to immutable signed
entries; full reservation and release; unavailable/overcommitted stock; concurrent
reservations (one succeeds); a deliberately stale late transaction guard rolling back
earlier steps; invalid increments/locations/companies/services; immutable Catalog kind;
archive/restore usage; reader denial; unique Sales full-line claims and owner attachment;
disabled optional owners; Finance capability refusal, duplicate protection, exact
balanced entries including zero cost, and atomic Finance reversal. Snapshot values
use exact decimal strings; balance quantities use integer ticks. The exposed current
standard-cost estimate is not presented as the sum of separately rounded postings.

Actual SDK identity HTTP checks validate the pinned SDK schemas, forged caller-header
and hostile-origin refusal, strict positive integer versions and Finance valuation
read detail. The schema test caught and fixed underscores in discovery column IDs.
Local TestClient uses a real loopback client address, not a bypassed local guard.

Every owned column has label/description metadata. Two human search phrases per
model find the correct table in the first five actual local catalog hits (mostly first).
Ruff and strict Inventory/Finance MkDocs builds pass.

Reproduce with exact INVENTORY_LOCAL_SOURCE_UID, SALES_LOCAL_SOURCE_UID and
FINANCE_LOCAL_SOURCE_UID:

```bash
.venv/bin/python -m pytest tests/erp/inventory -q
.venv/bin/python -m tests.erp.inventory.run_browser --frontend <frontend-root>
.venv/bin/mkdocs build --strict -f documentation/inventory/mkdocs.yml
.venv/bin/mkdocs build --strict -f documentation/finance/mkdocs.yml
```

Full tests/erp regression also needs the other module source variables and established
local PostgreSQL binaries/libraries. Use Node 24, Playwright and Chrome for browser tests.

## Local deployment and companion artifact

Inventory serves on loopback 38731 and Finance 38681 with actual SDK identity. No
migration runs at startup. Base/Catalog remain prerequisites; Sales/Finance imports
and operations are optional. Cross-owner statements are authored by their owner and
joined only on the same verified source. No foreign storage imports occur in Inventory.

Real browser passes location and stock-item creation, receipt/preparation/completion,
Finance posting and entry read, full physical/financial return, zero stock readback,
Sales full-line delivery and source navigation, archive/restore, unsaved draft guard,
stale rename/reload and dropped committed movement creation response recovered by
original-UUID GET with exactly one POST. Selection is keyboard operable; initial test
waits now respect disabled dependent pickers before opening them. Other module browser
transports stay unused until deliberate Sales navigation. Six SDK viewports and both
themes pass; tablet screenshot visually reviewed.

Held/failed readiness, Retry and all four Help links pass. All **68 built guides** pass
shared General/Modules ordering, module navigation, desktop/mobile/light/dark and
footer/keyboard/new-tab/unsaved-draft checks. Existing ERP submenu/history/mobile
checks pass. Five Inventory guides are in the same artifact. Nine frontend unit files,
TypeScript, theme audit (8 CSS files), docs checks and combined Vite/Docusaurus build
pass. Existing size and Docusaurus update-check notices are non-failing.

## Limits and next gate

No OpenERP parity claim: flat locations, full one-line movements, fixed standard costs,
one full return and bounded fixed-role subledger are deliberate scope. Deferred
lot/serial/backorder/routing/cost features remain in the mapping. Production-engine
concurrency, hosted identities/grants/transport, platform resource selection and
release workflow remain unverified. The -inventory workflow candidate is inactive.
No platform migration, push, tag or deployment occurred. Purchasing may begin locally.
