# Sales functional review

Reviewed before the API ADR on 17 November 2026: `mart-e/openerp`, Odoo 14.0,
commit `b8c8006f649f9f33f271a9dfc1434bb8ffae8798`.

Sources: [orders and lines](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/sale/models/sale.py),
[optional CRM link](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/sale_crm/models/sale_order.py).
Inspected header/customer/company/currency fields, line quantities/prices/discounts,
amount calculation, quotation expiry, confirmation, cancellation, reset and
confirmed-line protection. This is source review, not an executed Odoo parity test.

| Functionality | Bounded release decision |
| --- | --- |
| Customer, operating company and currency | Base-owned references; Sales stores versioned snapshots for historical meaning. |
| Product/service, units, quantity, price and discount | Catalog references and immutable unit meaning; explicit decimal prices, positive quantities, 0–100% discount, currency-rounded net totals. |
| Draft, sent, confirmed, cancelled and reset | Implement draft/quoted/confirmed/cancelled. Mark quoted records an externally communicated quote; it sends no email. Confirm freezes commercial terms; cancel is denied once downstream usage is linked. Return quoted or cancelled unused orders to draft. |
| Validity and confirmation date | Expired quotations cannot confirm; server owns UTC confirmation time. |
| CRM opportunity reference | Optional integration; ordinary Sales has no CRM dependency. Read the authorized CRM opportunity before linking it; preserve its identifier and name. |
| Order numbers | Unique operator-entered reference in this release. Base numbering remains its own operation; no legal or gapless numbering claim. |
| Taxes, fiscal positions, invoices and payment terms | Finance owns the next-stage implementation; this release explicitly displays net amounts and does not claim a tax total or invoice. |
| Pricelists, templates, variant configuration, signatures and customer portal | Deferred to later Sales/Catalog/Commerce releases, with no placeholder actions. |
| Deliveries, service work and invoiced quantities | Introduced by later owning modules through explicit public contracts and linked records, never by writing Sales tables directly. |

Implementation and executed evidence are tracked separately in the module status
and verification documents; these decisions alone do not establish completion.
