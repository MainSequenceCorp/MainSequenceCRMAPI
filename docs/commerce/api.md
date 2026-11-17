# API contracts

Private prefix /api/commerce/v1 uses SDK-verified identity and independent commerce.read,
write, manage and configure capabilities. Readers inspect collections; configure edits
publication; manage issues/revokes access and invoices. Owner Sales/Finance capabilities
are also enforced. Strict payloads reject unknown fields and boolean versions.

| Route | Contract |
| --- | --- |
| GET ready/ | own revision/source, required owner readiness, optional Sales/Finance flags |
| GET sites/, offers/, grants/, checkouts/ | SDK 0.5.19 collections, page_index/page_size/search/state |
| GET resource/discovery/, resource/uid/, resource/uid/audit/ | typed discovery, safe detail, manager-only recent audit |
| POST sites/; PUT sites/uid/ | request_uid or expected_version; name, slug, body, operating_company_uid, currency_uid |
| POST offers/; PUT offers/uid/ | request_uid or expected_version; site_uid, item_uid, name, description, unit_price |
| POST sites/uid/publish/ or unpublish/; offers equivalent | expected_version |
| POST grants/ | request_uid, site_uid, customer_uid; returns safe grant and one-time token |
| POST grants/uid/revoke/ | expected_version |
| POST checkouts/uid/invoice/ | request_uid, expected_version, invoice reference/dates and explicit tax percentage |
| GET checkouts/uid/payment/ | Finance-owned recorded payment projection |
| GET references/sites/, companies/, currencies/, customers/, items/ | owner-authorized picker collections |

Local customer prefix /api/commerce-public/v1 exposes GET sites/slug/ (published fields
only), GET/POST checkouts/ and GET checkouts/uid/. Portal routes require X-Portal-Token;
no customer-supplied platform identity is accepted. Lists accept only pagination; no
credential query parameter. Customer app has no internal routes, docs/OpenAPI endpoint
or private API proxy. All responses no-store/no-referrer. Published content is plaintext.

Checkout body has request_uid, expected_site_version and 1–20 lines, each offer_uid,
expected_version, quantity (decimal string). Prices/customer/company/currency are
server-resolved; injected fields fail. Response hides customer/grant/owner identifiers
and private snapshots, exposing order reference, exact net total, service lines and
recorded payment state. Original-UUID lookup is scoped to the current access code.

403 means missing/expired/revoked access; 404 missing/inaccessible record; 409 stale
version, conflicting request or state; 422 invalid input; 503 unavailable owner/source
or SDK identity. Business errors use error.code/message; framework validation uses
FastAPI detail. Never automatically replay uncertain writes: GET original UUID first.
