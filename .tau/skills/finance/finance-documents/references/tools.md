# Available MCP tools

Confirm the exact schema with `erp_tools_describe`. The current catalogue reflects access and module readiness.

- `finance_allocations_create` — Allocate an amount between two posted documents using both expected versions.
- `finance_allocations_list` — List allocations for one invoice or payment UID.
- `finance_inventory_valuations_get` — Read the two posting legs for a valued stock movement.
- `finance_inventory_valuations_list` — List Finance entries for inventory valuations.
- `finance_invoices_create` — Create a draft in invoices and vendor bills.
- `finance_invoices_create_from_sales` — Create one draft invoice from a confirmed Sales order and link both records atomically.
- `finance_invoices_get` — Read one of the invoices and vendor bills by UID.
- `finance_invoices_list` — Find Finance invoices and vendor bills.
- `finance_invoices_update` — Edit a draft in invoices and vendor bills.
- `finance_payments_create` — Create a draft in recorded payments.
- `finance_payments_get` — Read one of the recorded payments by UID.
- `finance_payments_list` — Find Finance recorded payments.
- `finance_payments_update` — Edit a draft in recorded payments.
