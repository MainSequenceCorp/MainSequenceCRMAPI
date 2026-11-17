# ADR 0002: owner-authored purchase receipts

Accepted for local implementation, 17 November 2026. Supports Purchasing ADR 0001
and the reviewed OpenERP purchase_stock receipt flow. No Inventory DDL change.
Expose a complete public service plan for a full purchase-line physical receipt:
validate stock policy/company/product/unit, supplier → internal locations, exact
quantity and caller source identifiers, then author the movement and audit.
Purchase origin is retained in the existing immutable movement snapshot. Purchasing
joins its own unique line claim in the same guarded transaction/DataSource.
Expose a completed/unreturned movement version fence for received-only billing.
Inventory remains the sole movement, balance, return and valuation writer. A later
return does not automatically reverse a vendor bill. Existing standalone and Sales
movement APIs remain compatible. Verify integration and return/billing concurrency.
