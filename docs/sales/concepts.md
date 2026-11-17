# Sales concepts and business rules

An order aggregates its customer, operating company, currency, commercial
reference, expiry, terms and ordered lines. Base owns referenced identities,
companies and currencies. Catalog owns items, categories and units. Sales never
writes these owners' tables or adds revisions to their migration streams.

Sales owns `erp_sales__order`, `erp_sales__order_line`, `erp_sales__audit_event`
and its independent Alembic version table. Lines reference only their own parent
by foreign key. Other domains are referenced through validated UUIDs and snapshots.

## Amounts and snapshots

Quantities and prices are decimal strings with at most 18 integer and 12 fractional
digits. Quantity is positive, price nonnegative, discount in [0,100]. A line's
net amount is quantity × price × (1 − discount/100), rounded to Base currency
precision using its configured half-up or half-even rounding. Total is the sum
of rounded lines. No tax, exchange-rate, invoice or legal numbering claim.
Up to 100 lines may be saved, including an empty draft. Marking quoted and
confirmation require at least one line and a nonexpired validity date.

Save and confirmation revalidate active customer/company/currency/item/unit/category
references and sale eligibility. Snapshots retain names, versions and unit meaning.
Reads from other modules are point-in-time observations, not a distributed lock.
Confirmation refreshes snapshots while retaining line identifiers. Commercial
terms become immutable. Update of a draft replaces its lines atomically.

## Lifecycle and concurrency

Drafts can become quoted or confirmed. Quoted records can return to draft or
confirm. Draft/quoted/confirmed records can cancel; cancelled records can reopen.
Quoted records reflect external communication and never send mail automatically.
Cancellation/reopening is denied if a downstream reference has been registered.
The Sales-owned `Service.attach` operation requires configure access, expected
version, a permitted consumer and UUID; a duplicate identical link is harmless.
It is an owner service contract for future integrations, not a mounted HTTP route.

Each mutation atomically guards current version/state, changes parent/lines and
appends audit. Stale versions return 409. Client creation UUID becomes order UID;
it is a reconciliation key, not automatic retry/idempotency middleware. On an
uncertain response, GET that UID before retrying. No destructive API delete exists.

## Optional CRM linkage

Sales reads the authorized opportunity through CRM's public API. For an
opportunity with a company, the selected Base customer's public `consumers.crm`
claim must be active, have logical kind `company`, and match that CRM company UID.
This preserves CRM's existing company contract; it does not assume a `party_uid`
field exists on the CRM response. Archived opportunities/companies are rejected.
CRM access is attempted only when listing or selecting a link. Unlinked Sales
continues when CRM is disabled. Hosted CRM linkage needs a separately verified
transport binding; the present integration is deliberately local-only.

## Explicit scope limits

This bounded release omits taxes, payment terms, invoices, deliveries, prices by
customer, product variants, quote templates, portal signatures and email sending.
The source mapping records the future owners. Existing local CRM board/deal-write
paths still contain PostgreSQL-specific SQL; Sales read-link evidence does not
establish their SQLite portability.
