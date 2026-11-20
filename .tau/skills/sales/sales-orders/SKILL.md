---
name: sales-orders
description: Find, edit and confirm Sales quotations and orders with their owner-side version and downstream checks.
---

# Sales Orders

Find the quotation with `sales_orders_list` and read the exact order with
`sales_orders_get`. Confirm the customer, company, currency, validity,
line quantities and prices before creating or updating a draft. Use the
current version when quoting, confirming, cancelling or reopening. The
owner rejects confirmation without lines and protects downstream records.
For an authorized draft invoice, use the Finance skill and its single
Sales-to-Finance command. Check the returned order and invoice references.

Consult the [tool reference](references/tools.md) and the live MCP schema before calling a tool.
