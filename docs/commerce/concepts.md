# Publication, customer access and commercial ownership

Commerce owns Site, Offer, PortalGrant, Checkout and AuditEvent. Namespace erp-commerce,
independent metadata/provider/history/version table. Base owns customer/company/currency;
Catalog owns services/units; Sales owns commercial orders; Finance owns invoices and
recorded payments. Commerce imports no foreign models. Owner-authored complete plans
join one guarded same-source transaction, including every affected owner's audit.

Only published plaintext sites and offers are public. Unpublish before editing content;
site slug/company/currency and offer site/item are immutable. Only active saleable
services can be offered. Customer quantities must match the Catalog default unit
increment; server-owned published prices determine exact Sales-rounded amounts.

A manager issues a 30-minute, revocable grant for one existing customer and site. A
256-bit secret is returned once; only its SHA256 digest persists. Never store the code
in logs, URLs, audit values or browser storage. The customer view holds it only in tab
memory and sends it in X-Portal-Token. Portal history is scoped to that exact grant,
including when two grants belong to the same customer. Internal platform identity is
resolved independently by the standard SDK middleware at the local merchant boundary.

Checkout atomically creates a frozen record and one confirmed service-only Sales order.
The request UUID identifies recovery; matching canonical input replays the same saved
result within the grant; changed input conflicts. Site/offer versions and grant fences
prevent concurrent revocation/unpublication from committing stale orders. Up to 20
unique services fit the transaction limit. Confirmed checkout does not process payment.

Merchant managers can hand off one draft invoice to Finance. Finance posts invoices,
records observed receipts, allocates them and reverses allocations. The portal projects
only scoped order and invoice summaries; paid means full allocation to a posted invoice.
No payment card processing, hosted public ingress, email delivery, public registration,
shipping, physical inventory fulfillment, refunds, promotions or automatic tax engine.
These omissions are explicit in the OpenERP coverage review; no full parity claim.
