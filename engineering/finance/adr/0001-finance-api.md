# ADR 0001 — Finance invoices, recorded payments and allocations API

17 November 2026. Accepted for local implementation after the
[functionality review](../openerp-coverage.md). Sales local cycle is complete in
API commit `7999317`, paired frontend `89e2fb6`. No platform release is approved.

## Ownership and initial accounting boundary

Finance owns invoice/bill aggregates and lines, payment records, allocations,
posting entries and audit, with independent SQLAlchemy metadata, namespace
`erp-finance`, prefix `erp_finance__`, provider `src.erp.finance.migrations:migration`
and version table `erp_finance__alembic_version`. Base is the only required
business dependency. Optional Sales linking is isolated in an integration adapter.
No CRM data-model dependency and no new Agent or MCP functionality.

The first accounting boundary is an operational receivable/payable subledger.
Fixed posting roles are receivable, payable, income, expense, tax payable, tax
recoverable and bank. Every posted invoice/payment and reversal balances exactly
by company and currency. A configurable chart/journals, statutory reports, fiscal
positions, bank settlement and legal document numbering remain later work. Never
present a payment record as evidence of an executed bank transfer.

## Objects, rules and API

`/api/finance/v1/invoices/` and `payments/` expose normalized collection/discovery,
detail, create and full draft replacement. Each aggregate carries a version and
client-supplied creation UUID; uncertain writes must reconcile by UUID before any
retry. Strict unknown-field rejection and Decimal strings follow Sales contracts.
POST action routes post or void, and explicit allocation commands allocate/unallocate.
References and readiness expose authorized Base reads; optional order references
require Sales access. Audit requires configure permission.

Invoices use kind customer/vendor, active party/company/currency, manual unique
reference, invoice and due dates, notes and at most 100 description/quantity/price/
discount/tax-rate lines. Require company currency. Quantity > 0, price >= 0,
discount/tax percentage in [0,100]. Currency-rounded net and tax are calculated
per line and summed; total must be positive for posting. Dates cannot put due date
before invoice date, and future-dated records cannot post. Snapshot Base identity,
precision and versions on save; validate current active references on posting
without silently changing the saved monetary calculation. Changed currency
precision requires draft review. Posted terms and original entries are immutable.

Payments independently record customer inbound/vendor outbound amounts, dates,
party/company/currency and external reference. Positive amounts must already fit
currency precision. Posting creates liquidity and receivable/payable counterpart
entries. It does not contact a bank or send a payment instruction.

An allocation links matching posted invoice/payment kind, party, company and
currency. Amount is positive and cannot exceed either remaining balance. The
same transaction guards both expected versions, increments both, writes allocation
and audit. Reverse allocation retains its record and restores balances with the
same guards. Void of a posted record requires zero active allocated amount and
writes opposite entries atomically; original entries/history remain visible.
Voided records cannot reopen. No destructive business delete API exists.

## Optional Sales integration

The Finance-owned from-Sales command accepts client UUID, invoice reference/dates,
order UID and expected order version, plus an explicit simple tax percentage.
Read a confirmed order and copy its stable customer/company/currency and lines;
reject a currency precision change that would alter its recorded net amounts.
One source order can produce one full invoice, including retained void history;
partial/delivery invoicing is deferred. Source terms cannot be edited independently
on the invoice. Tax/due date/reference remain Finance-owned draft terms.

Extend Sales with an owner-authored `plan_attach` operation returning governed
statements. It retains Sales authorization, confirmed-state/version guards and
audit. Finance composes that public plan with its invoice creation only after
verifying the same MetaTables DataSource. Both commit atomically. Finance never
imports Sales storage models or handwrites its tables. A duplicate request/source
conflicts; GET reconciles uncertain outcomes. Sales retains the historical link,
so its cancellation guard remains conservative even after an invoice is voided.
Optional integration may be disabled; unlinked Finance stays operational.

## Permissions, delivery and verification

Use existing verified requester/caller and platform Teams for finance.read,
finance.write, finance.post and finance.configure. Read references additionally
requires Base read. Posting/reversal/allocation requires finance.post. Sales link
creation additionally requires Sales configure/read; confirmed order snapshots avoid a new Catalog dependency.
All deterministic operations remain backend APIs independent of the frontend.

Apply only Finance migrations to actual ready local MetaTables SQLite with the
exact source guard. Launch the first API on 38681. Verify strict inputs, rounding,
balanced postings, states, stale/concurrent allocations, insufficient balances,
reversal, atomic rollback, optional integration and source/schema isolation.
Check HTTP contracts against pinned SDK fixtures and actual local identity.
Companion frontend owns separate module screens, conflict/uncertain recovery and
its help under the shared General/Modules sidebar. Complete tests, local deployment,
frontend/browser verification and all stage documentation before Projects starts.
No push, release tag, active workflow, hosted migration or deployment is authorized.
