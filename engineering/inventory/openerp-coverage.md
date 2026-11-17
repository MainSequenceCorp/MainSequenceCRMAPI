# Inventory functionality review — before ADR

Reviewed 17 November 2026 at mart-e/openerp commit
`b8c8006f649f9f33f271a9dfc1434bb8ffae8798` (Odoo 14 lineage).
Four local catalog searches for warehouse balances, receipts/movements, reserved
quantity and valuation found Catalog/Sales/Finance definitions and unrelated
financial portfolios, not an owner of physical stock. Catalog remains product/unit
owner; Base remains company/currency owner.

| Reviewed source | Behavior | Bounded local adaptation |
| --- | --- | --- |
| [stock_move.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/stock/models/stock_move.py) | Draft/confirmed/assigned/done/cancelled, quantity/UoM constraints, reservation, completion, return instead of cancelling completed stock | One product per explicit movement, draft/ready/done/cancelled, exact stock-unit increments, full reservation before completion; immutable posted movements and explicit full compensating return. |
| [stock_quant.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/stock/models/stock_quant.py) | Product/location grain with optional lot/owner/package, on hand minus reserved, row-locked reservation, count adjustments create moves | One company/product/location balance, guarded versions, nonnegative available stock, adjustment locations and mandatory reasons; no direct balance edits. |
| [stock_location.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/stock/models/stock_location.py) | Internal/vendor/customer/inventory/production/transit semantics, company and hierarchical structure | Flat company locations: internal/vendor/customer/adjustment. Only internal locations hold balances; source/destination determine receipt, transfer, delivery or adjustment. Hierarchy, transit and production routes deferred. |
| [stock_picking.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/stock/models/stock_picking.py) | Grouped transfers, validation, partial quantities/backorders, operation type | Explicit one-line movements complete in full; no implicit partial/backorder creation. Multi-line pickings, wave picking, barcode flows and scheduling deferred. |
| [sale_order.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/sale_stock/models/sale_order.py) | Procurement launch and delivered quantity derived from completed outgoing/return moves | Optional one full-line delivery claim from a confirmed Sales order, owner-authored Sales attachment in the same transaction; Inventory owns completion/return trace. No change to Sales invoicing policy or its order status. |
| [stock_account/stock_move.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/stock_account/models/stock_move.py) | Separate valuation layers, inbound/outbound costs, standard/average/FIFO, balanced accounting entries, return original cost | Immutable per-company product standard-cost setup, signed stock entries and explicit Finance-owned balanced subledger handoff. Not statutory accounting, FIFO/average cost or configurable chart mapping. |

Future Inventory releases own lot/serial/package tracking, expiry, counts workflow,
reorder rules, partial/backorder and return allocation, cost changes/revaluation,
landed costs and intercompany transfers. Manufacturing will extend the production
integration through Inventory public plans. Purchasing will own supplier order
receipts and commerce will use Sales fulfillment. No new Agent/MCP or platform rollout.
Status: the selected bounded adaptations are implemented and locally verified.
Deferred features remain outside this release. See [executed evidence](verification.md).
