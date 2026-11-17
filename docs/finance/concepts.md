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
