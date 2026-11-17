# Finance local verification

17 November 2026. Source review preceded API ADR and development. Local verification
uses actual MetaTables Local SQLite, ready/active, exact DataSource
`75b7fd29-3b1f-565d-be8d-a3a27d643de2`, existing SDK identity and governed statements.
No client database engine or hosted mutation fallback was introduced.

## Runtime and migration evidence

Finance has six owned tables, its own namespace and Alembic provider/version table,
revision 0001. The official scaffold and revision were reviewed and formatted before
local application. Repeat upgrade preserves other module version bindings; a fresh
process reads saved Finance data. Core Finance imports no CRM, Catalog or Sales
package and requires only Base. Sales integration is lazy and optional.

Local Finance API runs on 38681 and Vite's `/api/finance` proxy reaches it. Readiness
checks the applied revision, source and Base bindings; the local identity wrapper
rejects forged identity and foreign origins. Hosted entrypoint remains `main.py`.
The inactive workflow example is outside platform discovery and is not approved
or platform-validated. It selects only `-finance` tags and its own migration job.

## Executed checks

Initial 25 Finance/Sales tests passed. The browser then found a missing Payment
import in the newly added allocation labels; it was fixed before completion.
The new long-history fixture initially exceeded the SDK statement limit and used
a wrong creator field; fixture batching/field names were corrected. Owned fixture
cleanup runs even after failure. Final full ERP regression: **504 passed**, no skips, 41 existing deprecation
warnings in 111.28 seconds. Log: `/tmp/erp-finance-regression.log`. This includes
all 13 Finance scenarios and the 13 Sales scenarios.

Real browser creation, exact tax totals, concurrent edit conflict and reload,
dirty-navigation protection, immutable posted terms, partial/full allocations,
reversal, voiding and the confirmed Sales order → invoice link passed. Six SDK
viewports in light/dark modes passed. Independent frontend transport was verified
with CRM/Sales/Catalog browser requests blocked; Finance's owner integration still
runs behind its own API. Held/failed readiness and explicit Retry passed.

Frontend nine unit files, TypeScript, combined Vite/Docusaurus build, theme audit,
all 50 guides and strict backend MkDocs build passed. All built guide pages were
checked on desktop/mobile in both themes, with shared General then Modules,
cross-module links, Settings, keyboard Documentation link, new-tab behavior and
dirty-form guards. Existing CRM/Directory/Settings navigation/history passed.

The extended real browser run also passed older-allocation pagination and reversal,
and a real committed payment with its response deliberately dropped. **Check saved
record** recovered the original UUID; the mutation ran exactly once. All owned
fixtures were removed after each run. Ruff and diff whitespace checks pass.

## Reproduction and limitations

Use `docs/finance/delivery.md` for source verification, migration and API launch.
Set both FINANCE_LOCAL_SOURCE_UID and SALES_LOCAL_SOURCE_UID to the exact source
above. Run `python -m pytest tests/erp/finance tests/erp/sales -q` in the API venv.
The full ERP suite additionally needs the existing local PostgreSQL test binaries
and libraries described in Sales verification for older CRM compatibility tests.
New Finance mutations use MetaTables Local SQLite.

Run `python -m tests.erp.finance.run_browser --frontend <paired-frontend-root>`
with Node 24 and Playwright available. The frontend evidence index lists commands
for startup, docs and existing navigation. Browser fixtures are scoped to owned
UUIDs; historical allocation fixtures are clearly seeded local data.

This is a bounded operational subledger, not full OpenERP Accounting parity.
Simple explicit tax, company currency, fixed account roles and one full invoice
per order are deliberate adaptations. General ledger configuration, localization,
statutory reporting, FX, bank execution, credit notes and partial order billing
remain future Finance work in the source mapping. SQLite checks do not establish
production-engine locking or legal/accounting sufficiency. Hosted access, Teams,
workload grants, production engine, exact release binding and deployment remain
unverified and require separate user approval. No push, release tag, hosted
migration, active workflow or platform deployment occurred.
