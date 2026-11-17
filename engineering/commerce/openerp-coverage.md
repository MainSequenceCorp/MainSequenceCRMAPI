# Website and commerce functionality review

Reviewed before ADR/development, 17 November 2026. Supplied mart-e/openerp commit
`b8c8006f649f9f33f271a9dfc1434bb8ffae8798`. Existing local metadata search found Sales,
Finance and Inventory source records, but no owned website/offer/portal/checkout tables.

| Source inspected | Behavior | Initial adaptation |
| --- | --- | --- |
| [website_page.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/website/models/website_page.py), _compute_visible/save_page_info/write | Published visibility, URLs, page content, website ownership and cache invalidation | Owned plaintext landing page per site, stable unique slug, explicit publish/unpublish and no-store local public reads. No arbitrary HTML or template execution. |
| [website_sale sale_order.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/website_sale/models/sale_order.py), _cart_update/_compute_cart_info | Draft cart lines, product eligibility, quantities and service-only classification | Customer-side cart of published service offers; server-authoritative prices/quantities and atomic creation of one confirmed Sales order per checkout. |
| [portal.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/portal/controllers/portal.py), _document_check_access | Access-rule or explicit token-gated document access | Short-lived, revocable, hashed portal grant scoped to one site/customer; public endpoints expose only published fields or grant-owned checkout summaries. No internal ERP grants for customers. |
| [website_sale controllers](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/website_sale/controllers/main.py), checkout/confirm/payment routes | Customer checkout, order confirmation and payment-state flow | Local service checkout, operator-owned invoice handoff and portal projection of actual Finance allocations; no payment processor or simulated successful payment. |

Finance remains the authority for invoices, recorded receipts and allocations. Catalog
owns service definitions/units. Sales owns commercial orders and later service delivery.
Physical-product checkout is excluded until an explicit Inventory availability,
reservation and fulfillment design is implemented. The internal ERP and customer
surfaces share one static artifact, with distinct navigation and access.

Deferred: public account registration, email invitations, hosted ingress, card/bank
processing, automatic taxation, shipping, physical stock promises, discounts/pricelists,
website templates/editor, SEO redirects, multilingual sites, refunds and subscriptions.
This is a bounded local flow, not complete OpenERP website_sale parity.
