# Purchasing local verification — 17 November 2026

Actual MetaTables Local SQLite, local_mode true, class_type/dialect sqlite,
bootstrap active/ready and exact DataSource 75b7fd29-3b1f-565d-be8d-a3a27d643de2
were checked before migrations and fixture writes. Purchasing 0001 and Finance 0002
applied successfully. Own bindings/metadata/repeated setup/fresh-process persistence
are covered. Finance 0001 and Inventory 0001 were not rewritten.

Focused initial suite: six tests passed in 15.02 seconds. The final broader suite
includes a seventh owner-permission/wrong-source check. Full ERP regression:
**543 passed, 41 warnings in 205.77 seconds**.
Actual SQLite tests exercise RFQ/confirmation/closing/cancellation, exact purchase
unit conversion, rejected rounding/immutable Catalog assignments, product receipt,
service acceptance/revocation, disabled optional modules, Finance source locks,
full supplier returns and received-only bills. Concurrent acceptance has one winner.
A stale purchase claim rolls back a proposed Inventory movement; a return racing
with billing rolls back Finance and Purchasing together. Read-only owner profiles
cannot create receipts/bills. Forged headers, external origin/host and boolean
versions fail in actual SDK-authenticated HTTP tests. Pinned SDK 0.5.19 collection
and discovery schemas validate; wrong-source writes fail before mutation.

Local deployment: Purchasing 38741, restarted Finance 38681, Inventory 38731 and
Projects 38691 load the compatible Finance revision and owner extensions. The
Purchasing launcher uses the existing SDK sign-in and explicit source variable.
No credentials were copied to the frontend. Own ready transport is checked before
rendering module screens. First-start held/failed readiness and Retry pass.

Actual browser integration creates a two-line product/service purchase order,
marks RFQ ready, confirms, accepts service, creates/prepares/completes Inventory
receipt, creates a Finance vendor bill, verifies source quantity is locked, opens
source links and closes the order. Purchasing makes no direct frontend requests
to another domain until the user navigates there. Six SDK viewport layouts and
both themes pass. Uncertain committed order creation performs one POST followed
by original-UUID lookup; stale draft changes recover through reload. Dirty draft
navigation is guarded. Final visual review removes an empty action card and uses
snapshotted labels for locked reference fields.

Two user guides join all 70 built guides. General/Modules sidebar order, links,
Settings, feature Help/return, mobile/desktop, light/dark, keyboard/new-tab footer
and dirty navigation checks pass. Shared application submenu/history/mobile checks
pass. Nine frontend unit files, TypeScript, SDK theme audit (eight CSS files),
docs validation and combined Vite/Docusaurus build pass. Strict Purchasing, Finance
and Inventory MkDocs builds pass. Every owned column has label/description; two
human search phrases per model rank the intended table first in the local catalog.

Fixtures use public owner operations and explicit UID cleanup through governed
MetaTables transactions. Two test-harness import/initialization failures left
owned disposable reference batches; their exact IDs were recorded and removed
before passing reruns. Final browser runner cleans all fixture orders, receipts,
Finance drafts and Inventory movements, then prerequisites. No user records deleted.

Reproduce with PURCHASING_LOCAL_SOURCE_UID, INVENTORY_LOCAL_SOURCE_UID and
SALES_LOCAL_SOURCE_UID set to the source above, then `.venv/bin/python -m pytest
 tests/erp/purchasing -q`. Full tests/erp also sets the other module source variables
and uses the established local PostgreSQL fixture runtime for legacy CRM tests.
Distinguish that compatibility coverage from the new Local SQLite integrations.
Frontend: npm test, npm run docs:check, npm run build; API-owned
`tests.erp.purchasing.run_browser --frontend <checkout>` runs browser fixtures;
`tests/erp/purchasing/browser/startup.browser.mjs` and both tests/application suites
check startup and shared artifacts. Logs/screenshots retained under /tmp/purchasing-*.

Hosted engine/identity/grants/delegation, workflow reconciliation and platform release
remain unverified and require explicit approval. No push, tag, hosted migration or
platform deployment performed. Manufacturing follows after this local cycle closes.
