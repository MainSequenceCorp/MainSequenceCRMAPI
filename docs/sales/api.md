# HTTP API

Prefix `/api/sales/v1`. Install existing Main Sequence request identity once;
effective actor is the verified requester or caller. Organization administrators
have all Sales capabilities. `SALES_READER_TEAM_UIDS`, `SALES_WRITER_TEAM_UIDS`
and `SALES_ADMIN_TEAM_UIDS` map existing platform Teams to read, read/write and
all Sales capabilities. No new users or roles are stored. The authenticated local
wrapper grants its signed-in developer capabilities after validating local scope.

| Method and path | Contract |
| --- | --- |
| GET `ready/` | Sales revision/source/capabilities and Base/Catalog prerequisites. |
| GET `orders/discovery/` | Command Center resource discovery with search/status filter/columns. |
| GET `orders/` | Normalized collection; `page_index`, `page_size` (1–100), `search`, optional `state`. Unknown queries rejected. |
| POST `orders/` | Strict create input including `request_uid`; 201 with the aggregate. |
| GET `orders/{uid}/` | Current aggregate including ordered lines, snapshots, downstream references and version. |
| PUT `orders/{uid}/` | Full draft replacement with `expected_version`; returns updated aggregate. |
| POST `orders/{uid}/{action}/` | `quoted`, `confirm`, `cancel`, `reopen`; body contains only positive integer `expected_version`. |
| GET `references/{resource}/` | Paginated authorized owner reads: customers, companies, currencies, items, opportunities. |
| GET `audit/?record_uid={uid}` | Latest 100 audit events; requires `sales.configure`. |

Collection/discovery use the pinned Command Center schemas in
`tests/erp/sales/contracts/sdk-0.5.19`. Detail/command/readiness are application
contracts; exact input types are in OpenAPI at `/openapi.json`.

## Create/update fields

```json
{
  "request_uid": "<client-generated UUID>",
  "name": "Q-2026-001",
  "customer_uid": "<Base party UUID>",
  "operating_company_uid": "<Base operating company UUID>",
  "currency_uid": "<Base currency UUID>",
  "customer_reference": "Customer purchase reference",
  "valid_until": "2026-12-31",
  "notes": "Agreed commercial terms",
  "crm_deal_uid": null,
  "lines": [{"item_uid": "<Catalog item UUID>", "description": "Consulting", "quantity": "3", "unit_price": "12.50", "discount": "10"}]
}
```

Replace `request_uid` with `expected_version` for PUT. Reference accepts uppercase
letters/digits followed by uppercase letters/digits, dot, underscore, slash or
hyphen, up to 64 characters. Unknown fields, malformed decimals, caller-owned
state/audit/amounts, and invalid UUIDs are rejected. Returned amounts are exact
strings, timestamps are UTC, and a successful save increments the version.

## Errors and permissions

Sales read is required for collections/detail/discovery/references; write for
save and transitions; configure for audit and future owner linking. Base/Catalog
reads additionally enforce their own read permissions. API-authoritative checks
remain in effect regardless of disabled frontend buttons.

Domain failures have `{"error":{"code":"…","message":"…"}}`. Framework input
validation uses FastAPI's 422 `detail` list. Common statuses: 403 capability denied,
404 missing reference/record, 409 stale version/duplicate/invalid lifecycle or
downstream guard, 422 invalid business input, 503 unavailable storage/identity/CRM.
Clients must not automatically replay writes after a timeout or server error.

Finance integration uses the public owner-authored `Service.plan_attach` command
plan. It validates Sales permissions, confirmed state, version and link limits,
then returns guarded Sales statements plus its audit event for an atomic
same-DataSource transaction. Finance never imports Sales table models or writes
Sales tables independently. `attach` still executes that same plan for existing
callers. A failed Finance invoice insert rolls back the Sales link and version.

Commerce uses Sales' public `plan_commerce_checkout` (ADR 0002): independently requires
sales.write/configure, validates active Base/Catalog references and exact service terms,
and returns the entire confirmed order, lines and audit plan. Commerce joins it to
its grant/publication fences and Checkout insert on the same source. The existing
related-record map carries commerce:<checkout UUID>; no Sales DDL change. Public
customers cannot submit prices or confirmed Sales state directly.
