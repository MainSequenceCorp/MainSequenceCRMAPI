# ADR 0001 — Independent Inventory API

Accepted for local implementation, 17 November 2026, following the source review.
API extension only. No new Agent/MCP. All implementation and writes remain local.

## Ownership and precision

Inventory owns Location, StockItem, Balance, Move, Entry and AuditEvent, own metadata,
namespace erp-inventory, explicit migration provider and erp_inventory__alembic_version.
Base and Catalog are declared prerequisites. Sales and Finance integrations are lazy,
optional and separately disabled. Each owner retains its models and migration history.

A StockItem is a stock policy for one active Catalog product and Base operating
company, unique per pair, not a duplicate product definition. Its default unit,
rounding increment, company currency and standard unit cost are immutable snapshots.
Input quantities are decimal strings that must be exact positive multiples of the
snapshotted increment; convert to bounded integer ticks for atomic comparisons.
At most 10^12 ticks on a balance. No float arithmetic or silently rounded quantities.
Finance values use Decimal and the snapshotted currency precision. Cost revaluation
requires a later ADR, not an edit of historical stock policies. Catalog services are
rejected. Only names/codes of locations can change; company/type are immutable.

Locations belong to one company, have internal/supplier/customer/adjustment usage,
and unique company/code. Internal balances have unique stock-item/location, immutable
identity, on-hand and reserved ticks; zero balances are initialized transactionally
when a movement is created. Stock policy/location versions fence creation, archive
and mutations. Archive requires zero on hand/reserved and no open moves. Existing
histories retain snapshots and references. No foreign reference can cross company.

## Movement lifecycle and atomicity

One move has source, destination, stock item, exact quantity, reason/reference and
frozen labels/cost/unit/currency. Allowed pairs: supplier→internal receipt,
internal→customer delivery, internal→internal transfer, adjustment↔internal count
adjustment. No external→external or same-location move. Draft can be cancelled;
no implicit writes to balances or external parties. Prepare requires the whole
quantity available, reserves internal-source stock and sets ready. Complete requires
ready, consumes the source reservation, updates balances, writes immutable signed
entries and audit, and sets done atomically. Receipt preparation needs no reservation.
Cancellation releases only this move's reservation. Guard every version/state and
balance; competing operations or insufficient stock fail without partial updates.

Completed moves cannot be edited/cancelled. An explicit reasoned full reversal creates
a new done move with swapped locations, compensating entries and original linkage in
one transaction; it requires sufficient unreserved stock at the return source and
can occur once. A reversal cannot itself be reversed. Historical records remain.
If the original was handed to Finance, reversal includes the Finance-owned opposite
posting or fails entirely when Finance cannot authorize it. An unposted reversed
pair cannot later post only one half. Balances reconcile exactly to signed entries.

## Selected integrations

From Sales: select a confirmed order and product line, matching stock policy/company,
current unit UID and snapshot increment; create one full-quantity delivery to an
explicit customer location. Unique order-line claim prevents duplicate fulfillment;
partial shipments are deferred. The claim and Sales.plan_attach('inventory') run in
one governed transaction on the same source. Cancelled claims remain traceable; a
new commercial replacement needs a new order line. Standalone moves do not need Sales.

Finance handoff is explicit after completion, optional and same-source atomic.
Finance owns a new public service plan and read contract for inventory valuation:
fixed inventory and stock-clearing subledger roles, opposite signed amounts rounded
in company currency, unique per movement, with Finance audit. Inventory imports no
Finance model and never authors its writes. The move version and finance_posted flag
join the owner plan in one transaction. Internal transfers have zero net company
valuation; no posting is created. Zero-cost external movements retain zero entries
as traceable balanced postings. This is a bounded operational subledger, not a new
chart of accounts or statutory GL. Finance's extension has its own ADR/docs/tests.

## API and companion frontend

/api/inventory/v1 provides readiness, references, SDK discovery/collections,
locations/stock-items creation, location rename, archive/restore, movement creation,
prepare/complete/cancel/reverse, explicit Finance handoff, balances and immutable
entry/audit reads; from-sales takes order/line plus current order version. Create
requests carry stable UUIDs for uncertain-result lookup; changes carry strict positive
versions. Unknown fields and client identity/result fields are rejected. Existing
SDK verified identities govern inventory.read/write/manage/configure; no user store.
Manage performs stock commands, configure sets stock policies/locations. Optional
owner actions also require their own capabilities. Errors are 403/404/409/422/503.

The single ERP frontend adds Inventory with Movements, Stock balances, Stock items
and Locations; independent readiness/transport, versioned confirmations, exact input,
loading/errors/recovery and direct Help. Finance posting data remains owner-authorized
through its read contract. Four feature guides plus overview join General→Modules;
Settings stays last. ADR/concepts/API/operations/evidence stay engineering-owned.

## Exit evidence and deployment

Verify actual Local SQLite, ready bootstrap and exact source before migration/writes;
scaffold/review/apply only own history. Test initial/repeat migration, fresh binding,
receipt→transfer→delivery reconciliation, reservation/cancel/return, race/rollback,
invalid quantities/companies/services, archive fences, Sales uniqueness, Finance
posting/reversal and disabled integrations. Test actual HTTP identity/contracts and
browser mutation/recovery/navigation, theme/responsive, combined guides/build before
Purchasing. Inactive workflow candidate only, with own migration Job and -inventory
tag. Platform migrations, pushes/tags/reconciliation and deployment await approval.
