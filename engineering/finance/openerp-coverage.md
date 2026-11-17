# Finance functionality review

Reviewed on 17 November 2026, before the API ADR: `mart-e/openerp`, commit
`b8c8006f649f9f33f271a9dfc1434bb8ffae8798`, Odoo 14.0.

Sources:
- [Invoice/journal entries](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/account/models/account_move.py): move types, customer/vendor/company/currency, invoice lines, due amounts/payment states, `_check_balanced`, `_post`, `_reverse_moves`, partial reconciliation entry points.
- [Payments](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/account/models/account_payment.py): inbound/outbound customer/vendor classification, payment-to-journal relationship, liquidity/counterpart entries, posting/cancellation.
- [Sales invoice preparation](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/sale/models/sale.py): `_prepare_invoice`, `_create_invoices`, company/customer/currency inheritance and invoice lines.

| Reviewed behavior | Bounded first Finance release |
| --- | --- |
| Customer invoice / vendor bill | Independently entered draft documents with Base party/company/currency, lines and due date. |
| Amounts, discounts, tax | Decimal strings; rounded net and simple operator-entered tax percentage per line; sum gross total. No localization/rate advice, fiscal positions or compound/included taxes. |
| Posting and balance | Immutable posted document plus balanced Finance-owned posting entries, using fixed account roles for receivable/payable, income/expense, tax and bank. This is an operational subledger, not a configurable general ledger. |
| Payments and reconciliation | Record observed inbound customer receipts/outbound vendor payments, post balanced entries, allocate partially to matching posted invoices/bills, and reverse allocations with version fences. This records payment; it does not transfer money. |
| Reversal | Void unused drafts; reverse posted unpaid documents/payments with equal opposite entries retained alongside originals. Reverse active allocations first. Full credit-note/refund and lock-period workflows are deferred. |
| Order to invoice | Optional Sales integration creates one full invoice from confirmed terms, snapshots source identifiers, and atomically registers the Sales-owned downstream link through its owner command plan. Independent Finance requires only Base. |
| Numbering | Unique manually entered business references; no legal/gapless numbering claim. |
| Currency | Company currency only; reject cross-currency postings until FX accounting is designed. |
| Journals/chart/financial statements/bank feeds/tax filings | Later Finance releases. Reports in this release expose document balances and posting trace, without claiming statutory accounts. |
| Partial/delivery invoicing, deposits, grouped invoices, refund order quantities | Later Finance/Sales integrations; first release issues at most one full source invoice per order. |

All selected behaviors in this bounded release are implemented and locally verified;
see [executed evidence](verification.md). Deferred rows remain outside this release.
Source inspection is not an executed Odoo parity test; the ADR explains adaptations.

Existing-table discovery in the verified local runtime found Sales/CRM records
and portfolio-market ledgers, but no customer invoice/payment-allocation owner.
Those portfolio tables have a different domain and are not reused as Finance.
