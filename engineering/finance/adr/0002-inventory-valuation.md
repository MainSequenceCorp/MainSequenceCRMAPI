# ADR 0002 — Inventory valuation handoff

Accepted for local implementation, 17 November 2026, as the selected integration in
Inventory ADR 0001 after review of OpenERP stock_account/models/stock_move.py at
b8c8006f649f9f33f271a9dfc1434bb8ffae8798. No Agent/MCP changes.

Finance retains Posting and AuditEvent ownership. Add a public owner-authored plan
for Inventory to join a completed move's version fence and posting marker in one
same-source MetaTables transaction. Require finance.post, current Base company/
currency validation and exact bounded decimal input. Unique Posting resource,
record_uid, phase and account_role prevent double handoff. Always insert two rows,
including zero cost, debit-positive inventory and credit-positive stock-clearing
for receipt (opposite for outbound). Return movements use their own UID and opposite
amount. Internal transfers have no company valuation effect and are excluded.

No new physical columns or model are needed; Posting.resource already permits the
inventory source. Update model metadata through Finance's existing provider without
rewriting its applied revision. No importing or writing Inventory tables from Finance.
Provide read-only collection/detail of inventory postings under Finance permission;
the companion Inventory detail consumes the owner read through its optional adapter.
This is the existing bounded subledger, not statutory GL or configurable accounts.
Verify atomic rollback, duplicate guard, permission and exact balanced entries,
zero values and reversal in the actual local cross-module tests. Keep Finance's own
API/concepts/operations docs and regression evidence current. Hosted gate unchanged.
