# ADR 0001: independent Purchasing API

Accepted for local implementation, 17 November 2026. Based on the completed
[OpenERP functionality review](../openerp-coverage.md). No new Agents or MCP.

Purchasing owns Order, OrderLine, Receipt and AuditEvent under `erp-purchasing`,
with independent metadata, provider, migration history and version table.
Base and Catalog are its prerequisites. Inventory and Finance are lazy optional
owner adapters; service-only purchasing works with neither enabled.

Draft terms contain supplier, company, currency, due date, supplier reference and
up to 100 exact-decimal product/service lines. Catalog must permit purchasing.
Capture purchase/default units, conversion factors, increments and item kind.
Currency-rounded line amounts are summed exactly. Physical quantities must
convert exactly to the stock unit increment. No silent conversion rounding.
RFQ-ready/confirm revalidate references; confirmed terms are immutable. Cancel
is blocked once receipts or a bill exist. Reopening applies only to RFQ-ready or
unlinked cancelled orders. Closed means all lines were received at that instant;
subsequent physical returns remain visible and never generate automatic credits.

Service acceptance records reason, actor and time; revoke while confirmed and before billing retains
the receipt record. Physical receipts atomically join an Inventory-owned complete
movement plan with the Purchasing line claim. Each line has at most one retained
receipt, including cancelled/returned movements. Full receipt only; no backorders.
Inventory completes/returns its movements. Same-source checks and guarded versions
serialize integrations. Purchasing never authors foreign model writes.

Create one Finance-owned draft vendor bill only after all lines are received.
The transaction includes Inventory receipt version fences, the Purchasing bill
claim and Finance's public complete bill plan. Source commercial terms are locked
in Finance; tax/date remain Finance fields. A later return requires manual financial
review; automated refunds/credits are outside this release. Closing does not require
Finance. Bill creation after closing is permitted when receipt evidence still holds.

HTTP prefix `/api/purchasing/v1`: ready, resources/discovery, orders collections,
detail/create/update, rfq/confirm/cancel/reopen/close actions, line service acceptance,
acceptance revocation, physical receipt creation, fulfillment status, draft bill,
audit, and prerequisite pickers. Strict payloads reject identity/state injection.
Injected identity supplies purchasing.read/write/manage and independent owner
permissions; no local identity database. Every mutation uses exact versions and
atomic audit; client UUID recovery is lookup, never blind retry.

Tests use verified ready MetaTables Local SQLite and the expected DataSource.
Cover lifecycle/precision, physical and service receipts, returns, bill terms,
permissions, stale/concurrent writes and rollback, fresh migrations, disabled
integrations, HTTP identity and pinned SDK resource contracts. Companion frontend
and guides live in the single ERP artifact with General → Modules navigation.
Local deployment precedes browser verification; platform approval remains open.
