# Purchasing functionality review

Reviewed before ADR/development, 17 November 2026. Reference: the supplied
mart-e/openerp repository at `b8c8006f649f9f33f271a9dfc1434bb8ffae8798`.

| Source | Behavior reviewed | Selected adaptation |
| --- | --- | --- |
| [purchase.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/purchase/models/purchase.py) | RFQs, confirmation/approval, locked orders, supplier/currency, product lines, quantities received/invoiced and vendor bill creation | Own purchase aggregate; draft → RFQ ready → confirmed → closed, explicit cancellation. RFQ readiness does not send email. Immutable confirmed terms, one full receipt per line, one full received-order draft bill. |
| [purchase_stock/models/purchase.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/purchase_stock/models/purchase.py) | Purchase lines create stock movements; completed/returned moves determine receipt; purchase-to-stock units | Inventory owns physical receipts/returns; exact snapshotted unit conversion with incompatible precision rejected. Purchasing owns service acceptance. |
| [account_invoice.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/purchase/models/account_invoice.py) | Vendor bill lines retain purchase source; ordered/received billing policies | Finance authors vendor bills and retains distinct Purchasing source. This release uses received quantities only. |

The selected adaptations are implemented and locally verified; see
[verification](verification.md). Supplier price lists,
replenishment, tenders, multiple approvals, email delivery, partial receipts/bills,
backorders, automatic credits, foreign exchange and tax localization are deferred
to future Purchasing/Inventory/Finance releases. No enterprise parity claim.
Inventory standard cost remains independent of the negotiated purchase price.
