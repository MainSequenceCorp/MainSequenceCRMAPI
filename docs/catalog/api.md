# Catalog HTTP API

Prefix: `/api/catalog/v1`. All business routes require verified Main Sequence
identity. Production uses injected identity; the local wrapper uses the existing
SDK sign-in on a loopback-only server. Never send caller-created identity headers.

## Permissions

| Capability | Operations |
| --- | --- |
| `catalog.read` | Readiness, schemas, lists, discovery, detail and quantity conversion |
| `catalog.write` | Create/update/archive/restore items |
| `catalog.configure` | Create/update/archive/restore categories, units, groups; audit read |

Comma-separated Team UUID settings are `CATALOG_READER_TEAM_UIDS`,
`CATALOG_WRITER_TEAM_UIDS` and `CATALOG_ADMIN_TEAM_UIDS`. Writer includes read;
admin includes all three. Organization admins have all; other unconfigured hosted
users have none. Local mode gives the real SDK user all three capabilities.

## Endpoints

`{resource}` is `items`, `categories`, `units` or `unit-groups`.

| Method and relative path | Contract |
| --- | --- |
| `GET /ready/` | Ready only after identity, permission and owned schema/source bindings pass; reports module, schema revision `0002`, local flag, source UUID and capabilities |
| `GET /resources/` | Input JSON schemas and caller-specific `can_write`/`can_archive` |
| `GET /{resource}/discovery/` | `command-center.resource_discovery@v1` metadata |
| `GET /{resource}/` | `{items, pageInfo}` with pageIndex, pageSize, totalItems, hasNextPage, hasPreviousPage |
| `GET /{resource}/{uid}/` | Record including UUID, version, timestamps, actor UUIDs and archive state |
| `POST /{resource}/` | Create from strict input; returns created record with status 201 |
| `PUT /{resource}/{uid}/` | Full replacement input plus `expected_version`; returns updated record |
| `POST /{resource}/{uid}/archive/` | Body `{"expected_version": 1}`; returns archived record |
| `POST /{resource}/{uid}/restore/` | Body contains current expected version; returns restored record |
| `GET /audit/?record_uid={uid}&limit=50` | `{items}` for one record, newest first; limit 1–100 |
| `POST /convert/` | Read-only quantity conversion below |

Collection parameters: zero-based `page_index` (0–100000), `page_size` (1–100,
default 25), `search` (name/code, maximum 200 characters) and `archived` (default
false; true selects archived records only). Items additionally accept `kind`;
units accept `group_uid`. Unsupported collection/discovery fields return 422.
Ordering is stable by name then UUID; custom ordering and bulk actions are absent.
The running API's `/openapi.json` provides the generated request schemas.

## Strict inputs

All resources require `name` (1–200 characters) and `code` (1–64 uppercase ASCII
letters/digits plus dot, underscore or hyphen; first character alphanumeric).
Optional `description` defaults to empty and permits up to 4000 characters.
Unknown input fields are rejected. Server-managed UUID/version/actor/timestamps
cannot be supplied. PUT is replacement, not PATCH: omitted optional fields reset
to their defaults. Send the intended complete editable state.

- Group: common fields only.
- Category: common fields and optional `parent_uid` UUID.
- Unit: common fields, `group_uid`, positive decimal-string `factor` (default
  `"1"`), boolean `is_reference` (default false), positive decimal-string
  `rounding_increment` (default `"0.01"`). A reference must have factor `1`.
- Item: common fields, `kind`, `unit_uid`, `category_uid`, optional
  `purchase_unit_uid`, optional sales/purchase descriptions (each at most 4000
  characters), and booleans `saleable`/`purchasable` (default true).

Decimal inputs are ordinary strings with at most 18 integer digits and 12
fractional digits; scientific notation, numeric JSON values and nonfinite values
are rejected. Factor/increment must be positive. Quantities may be negative/zero.

Example item creation, replacing the example UUIDs with actual Catalog records:

```json
{
  "name": "Consulting hour",
  "code": "CONSULT-HOUR",
  "kind": "service",
  "unit_uid": "11111111-1111-4111-8111-111111111111",
  "category_uid": "22222222-2222-4222-8222-222222222222",
  "description": "Consulting services",
  "saleable": true,
  "purchasable": false
}
```

## Conversion

```json
{
  "quantity": "2",
  "from_unit_uid": "11111111-1111-4111-8111-111111111111",
  "to_unit_uid": "22222222-2222-4222-8222-222222222222",
  "rounding": "up"
}
```

Both actual UUIDs must name active units in one active group. Compute quantity ×
source factor ÷ target factor exactly, then round to the target increment.
`up` rounds away from zero; `half_up` rounds nearest with ties away from zero;
`half_even` rounds nearest with even-multiple ties. Default is `up`.
Response contains `quantity` as a fixed decimal string, `rounded`, both unit UUIDs
and versions, `rounding` and `rounding_increment`. Two dozen to Each with increment
`0.01` returns quantity `"24.00"` and rounded false. Conversion persists nothing.

## Failure and retry behavior

Domain errors use `{"error":{"code":"...","message":"..."}}`. Input validation
uses FastAPI's `detail` list. 403 means missing capability, 404 unknown record,
409 stale version/uniqueness/reference/archive conflict, 422 invalid input,
incompatible units, immutable fields or invalid hierarchy, and 503 unavailable
identity/storage. SDK authentication rejection can also return 401.

After 409, reload and review before another update. After a timeout or 5xx write,
the outcome may be unknown: read the existing record, or search the unique code
for a create, before retrying. There is no request-id deduplication contract.
The frontend blocks blind replay and exposes this recovery. `/healthz` reports
process liveness only; use `/ready/` for usable application readiness.
