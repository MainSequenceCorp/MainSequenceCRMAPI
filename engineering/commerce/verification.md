# Website and commerce verification — 17 November 2026

Actual mutation storage: MetaTables Local SQLite, source
75b7fd29-3b1f-565d-be8d-a3a27d643de2. Verified local_mode, SQLite dialect/class,
active/ready bootstrap and exact source before writes. Five owned models, own
metadata/provider/version table and revision 0001 freshly applied and repeated.
Applied revisions remain unchanged. Every column has label/description; two human
phrases per model rank its table first in the actual local catalog.

Seven focused integration tests passed in 23.88 seconds: publication and immutable
references; service-only exact quantities/prices; scoped grants, expiry/revocation
and secret non-disclosure; checkout replay/races/late rollback; 20-line atomic budget;
optional owners/independent permissions/same-source checks; invoice/payment allocation
and reversal reconciliation; SDK 0.5.19 private collection/discovery and real local
customer HTTP boundaries; independent fresh-process persistence. Source IDs and prices
cannot be supplied through customer payloads. Owner plans include owner audits.

Local first deployment: private Commerce API 38761; separate customer origin 38762
serving the same built ERP dist artifact, no private API proxy. Customer /shop/<slug>
has no ERP bootstrap/navigation. No second frontend build or StaticSite resource.
SDK verifies the locally signed-in merchant; portal codes never become platform
identity. No automatic migration at startup, hosted ingress, real payment processing,
push/tag/platform migration or deployment.

Actual final browser verification passes merchant create/publish/grant/checkout/invoice
and source navigation; isolated customer checkout and Finance-recorded paid projection;
private API denial, plaintext rendering and no token persistence; six SDK viewports and
both themes; original-UUID recovery with exactly one POST; stale reload, dirty navigation
and immediate revocation denial. Merchant/customer tablet screenshots were reviewed.
Long-reference wrapping and a small help touch target were corrected before the final
successful run. Expired/revoked portal refresh clears loaded customer data. Finance
observed-payment fixtures use its owner HTTP API; no real payment is processed.

Held/failed initial readiness, explicit Retry, all four feature Help links and return
navigation pass. All 78 built guides pass desktop/mobile/both themes with one shared
General → Modules sidebar, Website and commerce after Manufacturing and before Settings.
Footer Documentation, keyboard/new-tab/dirty guards and established ERP submenu/history/
mobile navigation pass. Nine frontend unit files, TypeScript, docs validation, theme
audit of nine CSS files, combined app/docs build and strict Commerce/Sales MkDocs pass.
Ruff passes for maintained Python source; generated applied revision import style is
excluded without rewriting the applied migration. Whitespace checks pass.

Full ERP run: 530 passed; one HTTP assertion and 26 setup errors were caused by SDK
users/me returning 503 (local-backend reported no available server). Readiness recovered;
all 27 affected checks passed in a serial rerun (80.12 seconds). Thus all 557 collected
ERP checks passed across the original run and targeted rerun; this is not presented
as one uninterrupted clean run.
New integrations use actual SQLite; the established legacy fixtures use local PostgreSQL.

Fixtures track exact disposable UUIDs and clean Finance children before invoices,
Commerce children before sites and Sales prerequisites. No user records are removed.
Reproduce focused tests with COMMERCE_LOCAL_SOURCE_UID and SALES_LOCAL_SOURCE_UID set
to the verified source, `.venv/bin/python -m pytest tests/erp/commerce -q`; API browser
runner `tests.erp.commerce.run_browser --frontend <paired checkout>`. Local logs and
screenshots are under /tmp/commerce-*. Hosted identity/engine/delegation, workflow/tag
selection and public deployment remain unverified and require explicit user approval.
