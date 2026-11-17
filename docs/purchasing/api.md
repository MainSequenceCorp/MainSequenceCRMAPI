# HTTP contracts

Prefix /api/purchasing/v1. SDK-injected identity; Purchasing read/write/manage/configure.
Readers list/detail/references; writers draft and transition; managers accept/revoke,
create physical receipts, close, bill and read audit. Owner permissions are additional.

| Endpoint | Payload / response |
| --- | --- |
| GET /ready/ | Own revision/source, Base/Catalog sources, capabilities, inventory_enabled, finance_enabled. |
| GET /orders/discovery/ | Pinned resource_discovery@v1. |
| GET /orders/ | resource_collection@v1 items/pageInfo, page_index/page_size 1–100/search/state. Unknown queries fail. |
| POST /orders/ | request_uid, name, supplier_uid, operating_company_uid, currency_uid, supplier_reference, expected_on nullable date, notes, lines. Returns complete order, 201. |
| GET /orders/{uid}/ | Order, ordered lines, retained receipts, version and optional bill_uid. |
| PUT /orders/{uid}/ | Same commercial fields, expected_version; current draft only. |
| POST /orders/{uid}/{rfq,confirm,cancel,reopen,close}/ | expected_version; complete updated order. |
| GET /orders/{uid}/fulfillment/ | Per-line receipt/movement, state, received and all_received. Physical links need Inventory read. |
| POST /orders/{uid}/lines/{line}/accept/ | expected_version, request_uid, reason. Full service acceptance. |
| POST /orders/{uid}/lines/{line}/revoke/ | expected_version, reason. Retained service revocation on a confirmed unbilled order. |
| POST /orders/{uid}/lines/{line}/receipt/ | expected_version, request_uid, name, stock_item_uid, source_uid, destination_uid. Quantity comes from source snapshot. |
| POST /orders/{uid}/bill/ | expected_version, request_uid, name, document_date, due_date, tax_rate decimal string. Full received-order Finance draft bill. |
| GET /references/{suppliers,companies,currencies,items,stock-items,locations}/ | Paged public owner reads; last two require optional Inventory. |
| GET /audit/?record_uid=UUID | Up to 100 recent immutable Purchasing events, manager permission. |

Each line contains item_uid, description (empty uses Catalog purchase description/name),
quantity positive decimal, unit_price nonnegative decimal, discount 0–100. Maximum 100
lines, 64-character uppercase order reference. State/identity/result fields are forbidden.
Versions are strict positive integers; booleans rejected. No float amounts.

Errors: 403 permission, 404 missing, 409 stale/locked/state/duplicate/receipt conflicts,
422 schema/reference/precision failures, 503 unavailable owner/runtime or different source.
Domain errors use error.code/message; validation failures use FastAPI detail. Do not retry
an uncertain mutation: GET the original order UID and inspect receipt/bill links. A new
order uses the original request_uid for GET recovery, not an automatic replay token.
