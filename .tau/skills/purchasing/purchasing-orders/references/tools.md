# Available MCP tools

Confirm the exact schema with `erp_tools_describe`. The current catalogue reflects access and module readiness.

- `purchasing_order_lines_accept_service` — Record accepted service against a specific purchase order line.
- `purchasing_order_lines_receive_stock` — Receive a physical delivery and link it to the purchase line in one transaction.
- `purchasing_order_lines_revoke_acceptance` — Revoke an eligible unbilled service acceptance.
- `purchasing_orders_cancel` — Apply the cancel transition to the selected purchase order.
- `purchasing_orders_close` — Apply the close transition to the selected purchase order.
- `purchasing_orders_confirm` — Apply the confirm transition to the selected purchase order.
- `purchasing_orders_create` — Create a draft supplier order.
- `purchasing_orders_create_vendor_bill` — Create a draft vendor bill from the purchase order and its eligible receipts or acceptances.
- `purchasing_orders_fulfillment` — Read receipt, service acceptance and billing progress.
- `purchasing_orders_get` — Read a purchase order, lines and handoff references.
- `purchasing_orders_list` — Find purchase orders.
- `purchasing_orders_reopen` — Apply the reopen transition to the selected purchase order.
- `purchasing_orders_request_quote` — Apply the rfq transition to the selected purchase order.
- `purchasing_orders_update` — Edit a draft supplier order.
