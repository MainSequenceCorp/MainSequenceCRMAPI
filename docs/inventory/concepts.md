# Stock concepts and invariants

A stock policy is unique by Catalog product and Base operating company. Only physical
products qualify. Unit, increment, company currency and standard cost are immutable
snapshots. A policy has its own stock lifecycle; it does not duplicate Catalog item
management. Locations belong to one company and have internal/supplier/customer/
adjustment usage. Only internal locations carry balances. No cross-company transfer.

All quantities travel as decimal strings. They must be exact positive multiples of
the stock increment and fit 10^12 integer ticks; balances remain nonnegative, with
reserved <= on hand. Available equals on hand minus reserved. No float calculations
or implicit quantity rounding. The standard_cost_estimate on a balance is rounded
current quantity times standard cost; it is not a sum of posted valuation entries.
Finance and stock entries round per movement, so sub-cent rounding can differ from
that estimate. Reconciliation of physical quantities uses immutable signed ticks.

Movement creation freezes product, unit, company, currency, location names/types and
cost, and initializes any missing zero balances atomically. Prepare reserves the full
internal-source quantity. Complete requires prepared state, consumes its reservation,
updates both internal balances and inserts entries/audit atomically. Cancellation
releases reservations. Draft content is immutable in this bounded release: cancel
and create a corrected movement. All concurrency guards fail without partial writes.

Done cannot be cancelled. A full return requires a reason, active configuration and
sufficient unreserved stock at its return source. The return swaps locations, creates
opposite entries and links the original in one transaction; only one full return is
allowed. Returns cannot themselves be returned. Archive requires zero physical stock,
zero reservation and no unfinished movements. Restore preserves history.

Optional Sales conversion creates one full-quantity delivery for a confirmed product
line, using the matching company/product/unit snapshot. Unit-version equality is
conservative even for renamed units. A unique line claim and Sales-owned attachment
commit together. Cancelled claims remain claimed; partial/replacement fulfillment
requires a later release or a new commercial line. Existing Sales invoicing behavior
is unchanged. Standalone stock does not depend on Sales availability.

Optional Finance handoff marks a completed external movement and joins the Finance
owner's two balanced inventory/stock-clearing entries in the same source transaction.
Finance post capability is required. Internal transfers are excluded; zero-cost
external moves keep two zero rows for traceability. If a posted move is returned,
the return's opposite Finance entries must succeed atomically too. An unposted
returned pair cannot later post one half. This is the existing bounded operational
subledger, not statutory GL, FIFO/average costing, revaluation or configurable chart
mapping. Read valuation entries requires Finance read capability.

Lots/serials/packages, hierarchies, transit, partial/backorders, procurement rules,
barcode picking, scheduled stock work, cost changes and multi-line picking are
explicit future scope. Production integration belongs to the Manufacturing stage;
supplier-order receipt creation to Purchasing. No new Agent/MCP is included.
