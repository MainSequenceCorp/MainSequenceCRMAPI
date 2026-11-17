# Finance HTTP API

Prefix `/api/finance/v1`. Existing verified requester/caller identity is authoritative.
Existing Teams in `FINANCE_READER_TEAM_UIDS`, `FINANCE_WRITER_TEAM_UIDS`,
`FINANCE_POSTER_TEAM_UIDS`, `FINANCE_ADMIN_TEAM_UIDS` grant respectively read,
read/write, read/write/post, or all Finance capabilities. Base reads additionally
require Base access. Sales conversion requires Sales configure/read access.

| Route | Behavior |
| --- | --- |
| GET `ready/` | Exact source/revision, capabilities, Base readiness, optional Sales flag. |
| GET `invoices/`, `payments/` | Normalized paginated search/status collections; discovery at `discovery/`. |
| POST `invoices/`, `payments/` | Strict independent draft creation with client `request_uid`, response 201. |
| GET / PUT `{resource}/{uid}/` | Detail or full draft replacement with `expected_version`. |
| POST `{resource}/{uid}/post/` | Positive `expected_version`; requires finance.post. |
| POST `{resource}/{uid}/void/` | Expected version and nonempty `reason`; requires finance.post. |
| POST `invoices/from-sales/` | Request UUID, order UID/version, invoice reference/dates and simple tax percentage. |
| GET `sales-orders/{uid}/` | Authorized optional Sales source read. |
| GET `references/{resource}/` | Parties, companies, currencies or optional confirmed orders. |
| POST `allocations/` | Request UUID, invoice/payment UUIDs, both expected versions, positive exact amount; response 201. |
| POST `allocations/{uid}/reverse/` | Both expected versions; reverses an active allocation. |
| GET `audit/` | Resource and record UID; latest 100 events, requires finance.configure. |

Draft common fields: name, kind (customer/vendor), party_uid,
operating_company_uid, currency_uid, document_date, notes. Invoice fields:
due_date and lines(description, quantity, unit_price, discount, tax_rate).
Payment fields: amount and external_reference. Decimal quantities/amounts are
strings, not JSON numbers. Unknown fields and caller-supplied state/amount totals
are rejected. OpenAPI is the exact command schema source.

Details include version, snapshots, total/allocated/remaining, payment_status,
allocation events and signed posting entries. Debit is positive; credit negative.
Domain errors use an error code/message envelope; input validation uses FastAPI's
422 detail list. 403 denies access; 404 is missing; 409 denotes stale state,
duplicate request/source/reference or insufficient balance; 422 invalid business
input; 503 unavailable dependency/runtime. No automatic mutation replay is allowed.
Reconcile uncertainty by reading the original creation UUID or latest allocation
state and both document versions before deciding whether to retry.

Allocation history is paginated through `GET /invoices/{uid}/allocations/` and
`GET /payments/{uid}/allocations/` using `page_index` and `page_size` (default 25,
maximum 100). Results use `items` and `pageInfo`, with stable created-time/UID order,
both document references, and retained active/reversed history. Detail embeds the
first page as `allocations` and `allocations_page_info`; older active allocations
remain reachable and reversible. Voided records retain original amounts and show
zero remaining balance with payment status `void`.

Projects billing uses public `Service.plan_from_sales`, which returns the invoice UID
and complete owner-authored guarded statements. It retains Finance validation/audit
and the Sales owner link plan; same-source callers commit the entire plan with their
own guard. Existing `from_sales` executes that plan and returns the saved invoice.
No schema or HTTP behavior changes. A failed caller guard rolls all owners back.
