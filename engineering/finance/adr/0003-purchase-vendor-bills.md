# ADR 0003: owner-authored vendor bills from Purchasing

Accepted for local implementation, 17 November 2026. Supports Purchasing ADR 0001
and the reviewed OpenERP vendor-bill source mapping. Finance adds its own revision
0002 with nullable unique `Invoice.source_purchase_order_uid`; the existing Sales
source is preserved. Applied revision 0001 remains unchanged.
An authorized public Finance service plan validates a confirmed/closed Purchasing
snapshot, authors a full draft vendor bill, lines/source snapshots and audit. The
caller must join its guarded source claim and receipt fences on the same DataSource.
Commercial source identities, quantities/prices/descriptions are immutable in draft;
dates/tax remain editable. Existing manual bills and Sales invoices remain compatible.
No new public arbitrary snapshot-write route. No automatic purchase-price valuation,
credit notes, exchange conversion or new Agent/MCP. Verify uniqueness, exact amounts,
permission independence, source locks and atomic rollback on Local SQLite before
restarting affected local consumers. Hosted migration requires explicit approval.
