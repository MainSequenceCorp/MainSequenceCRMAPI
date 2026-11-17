# ADR 0003: Inventory-owned production stock plans

Accepted locally, 17 November 2026. Manufacturing ADR 0001 follows reviewed OpenERP
raw-material → production → finished-stock movement semantics.

Inventory revision 0002 adds production location usage and production-in/out movement
kinds through its own constraint migration; applied 0001 remains unchanged. Public
complete batch planners reserve, cancel and finish up to eight unique component products
plus one distinct finished product. Production snapshots retain the Manufacturing order
identifier. Single-movement transition/reversal/posting routes reject coordinated moves.
These routes cannot break a production batch into partial stock changes.

Grouped current policy/location/movement fences, individual balance fences and multirow
entry/audit inserts stay within the governed transaction budget. Inventory remains sole
writer of stock models; Manufacturing joins its own version/state/audit statements on
the same DataSource. Finance posting uses its existing owner plan for each completed
movement, with one batch flag fence and audit; no new Finance model or migration.

Default units and immutable standard-cost snapshots govern quantities/values. Production
locations are virtual and have no stock balance; components reduce internal balances and
finished goods increase them. Actual-cost rollup, flexible consumption, partial completion,
scrap/disassembly and by-products are deferred. Existing standalone/Sales/Purchasing stock
flows remain compatible. Test maximum-size batches, concurrent availability, rollback,
reconciliation, individual-route refusal and optional Finance permission/disablement.
