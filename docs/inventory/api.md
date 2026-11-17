# HTTP contracts

Prefix /api/inventory/v1. The installed SDK verifies caller/requester identity;
capabilities are inventory.read/write/manage/configure. Existing authenticated local
user has the local development profile. Hosted Team configuration is unverified.
No client identity headers or result fields are accepted. Input objects forbid extras.

| Endpoint | Contract and permission |
| --- | --- |
| GET /ready/ | Read capability, active own bindings, Base/Catalog sources and optional integration flags. |
| GET /references/companies/, /items/, /orders/ | Public owner reads, paged; orders requires configured Sales. |
| GET /references/orders/{uid}/ | Owner-authorized Sales order and its immutable confirmed lines. |
| GET /{resource}/discovery/ | Pinned SDK resource_discovery@v1 for locations, stock-items, balances, movements. |
| GET /{resource}/ | SDK resource_collection@v1 items/pageInfo; page_index, page_size 1–100, search, state, include_archived, company and stock-item filters. |
| GET /{resource}/{uid}/ | Owner detail; movements include immutable stock entries. |
| POST /locations/ | Configure; request_uid, name, code, operating_company_uid, usage. |
| PUT /locations/{uid}/ | Configure; expected_version, name/code only. |
| POST /stock-items/ | Configure; request_uid, item_uid, operating_company_uid, unit_cost decimal string. |
| POST /{locations or stock-items}/{uid}/{archive or restore}/ | Configure; strict positive expected_version; archive usage guards. |
| POST /movements/ | Write; request_uid, name, stock_item_uid, source_uid, destination_uid, quantity decimal string, reason. |
| POST /movements/{uid}/{prepare or complete or cancel}/ | Manage; strict positive expected_version. |
| POST /movements/{uid}/reverse/ | Manage; request_uid, expected_version, reason; returns the newly completed compensating movement. |
| POST /from-sales/ | Manage plus Sales configure; request_uid, name, order_uid, line_uid, expected_order_version, stock_item_uid, source_uid, destination_uid. |
| POST /movements/{uid}/finance/ | Manage plus Finance post; expected_version; same-source atomic owner plan. |
| GET /movements/{uid}/finance/ | Inventory read and Finance read when posted; Finance-owned entry response. |
| GET /{resource}/{uid}/audit/ | Manage; paged immutable action/actor/version/field-name history. |

Creation UUID is an identity for uncertain-result GET, not an automatic replay token.
Repeated mutation may conflict; always read current state after lost responses. Versions
are positive integers (booleans rejected). Expected responses are 201 creation, 200
reads/commands; 403 policy, 404 missing, 409 stale/state/stock/uniqueness, 422 input or
reference mismatch, 503 unavailable dependency/runtime. Errors use error.code/message;
FastAPI schema failures use detail. Integration failure does not widen permissions.

Discovery/collection schemas and all pinned fixtures are recorded under
 tests/erp/inventory/contracts/sdk-0.5.19; other endpoints are application-owned.
Actual authenticated HTTP schema verification is part of the local acceptance suite.
