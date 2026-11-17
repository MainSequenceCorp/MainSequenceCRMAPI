# Finance concepts

Customer invoices and vendor bills contain a Base party, operating company,
company currency, dates, terms and up to 100 description/quantity/price/discount/
tax-percentage lines. Finance stores independent snapshots. Quantities are positive,
prices nonnegative, percentage values in [0,100]. Decimal strings allow 18 integer
and 12 fractional digits. Net and simple exclusive tax are rounded per line using
currency precision; rounded amounts are summed. Tax percentages are operator input,
not localized rate rules. Due date cannot precede document date.

Drafts can be edited. Posting requires positive value, active Base references,
unchanged currency precision and a date no later than today UTC. Posted terms and
entries are immutable. Draft cancellation retains history; voiding a posted unpaid
record adds opposite entries. No reopening or destructive business delete exists.

Payments record observed customer receipts or vendor payments and their external
reference. They do not initiate bank transfers. Posting balances bank against
receivable/payable. Invoices balance receivable against income/tax payable; bills
balance expense/tax recoverable against payable. Fixed account roles establish a
bounded subledger, not a configurable general ledger or financial statements.

Allocations require posted records with the same kind, party, company and currency.
Both expected versions guard remaining balances atomically with allocation/audit.
Amounts cannot exceed either remaining balance. Reversal retains allocation history
and restores balances; reverse active allocations before voiding either document.
Details show the latest 100 allocation events and all posting/reversal entries.

Optional Sales conversion copies one full confirmed order and registers a
Sales-owned downstream link in the same governed transaction. A unique source
reference prevents double invoicing even after voiding. The historical Sales link
remains, conservatively preventing order cancellation. Source identities, quantities,
prices and descriptions stay fixed; Finance controls tax/due date/reference/notes.
Sales supplies its own authorized version-fenced statements; Finance imports no
Sales table models. Both stores must resolve the same exact DataSource.

## Inventory valuation extension (locally verified)

Finance owns a service plan for explicit Inventory handoff. Completed external stock
movements join their version fence/marker with two balanced inventory/stock-clearing
postings and Finance audit in one same-source transaction. Finance post capability
and active company currency are required. Duplicate movements cannot post again.
Returns create opposite postings for their own UID atomically with Inventory return.
Internal transfers are excluded. Zero-cost movements retain two zero-value rows.
No foreign model writes or migration ownership moved to Inventory.

Read-only GET /api/finance/v1/inventory-valuations/ returns a paged list of inventory
legs; GET /api/finance/v1/inventory-valuations/{movement_uid}/ returns the balanced
pair. Both require Finance read. The write plan is a public Python owner contract,
not an endpoint accepting arbitrary client amounts. Companion Inventory detail
consumes the owner read through its optional adapter. No statutory GL is implied.

Purchasing can create one full received-order draft vendor bill through an authorized
Finance plan. Commercial source terms stay locked; dates/tax remain editable. Returns
require financial review and never imply automatic credits. Finance revision 0002
owns the nullable unique Purchasing source reference; existing manual/Sales flows remain.
