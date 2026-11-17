# Purchasing API

Independent supplier purchase orders, full physical/service receipts and received-order
vendor-bill handoff. Base owns parties/companies/currencies; Catalog owns purchasable
items/units; Inventory owns physical stock; Finance owns bills/payments. No new Agents/MCP.

See [concepts](concepts.md), [HTTP contracts](api.md) and [local operations](delivery.md).
The module evidence and OpenERP mapping live under engineering/purchasing. This bounded
release does not include partial receipts/bills, backorders, supplier price lists,
replenishment, email sending, multi-level approvals or automatic credits.
