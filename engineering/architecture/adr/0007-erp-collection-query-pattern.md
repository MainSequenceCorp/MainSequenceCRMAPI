# ADR 0007 · Shared ERP collection queries

**Date** 20 November 2026

**Status** Implemented for the primary collections in all 14 ERP modules.
The [local verification record](../verification/erp-collection-queries.md)
lists the migrated routes, specialized routes with separate read boundaries,
and populated PostgreSQL results. Section 1 records the pre-change
Production baseline. Promotion and Command Center timing remain open.

## 1. Problem and evidence

[ADR 0005](0005-single-erp-api-deployment.md) puts all ERP modules in one API
deployment. A user's list search still follows different code paths in each
module. The differences matter once tables have rows.

| Existing collection | Baseline data calls before module admission | Consequence |
| --- | --- | --- |
| CRM Contacts | 1 for matching IDs, exact total, page, and page enrichment | The query has the right basic shape. The policy lookup and HTTP transport still cost time. |
| Finance invoices and payments, Base parties, Sales orders | 2, one for count and one for rows | Two round trips. A commit between them can make the count and rows disagree. |
| Finance invoice or payment allocations | 3, parent existence, count, and rows | The nested route pays for the parent check separately even when the page is empty. |
| Inventory balances | 2 plus 3 per returned row, for the balance, stock item, and location | A 25-row page can issue 77 data reads. A zero-row page issues two. |
| Reporting collections | 2, both scoped to the creator | The owner predicate must remain in the shared count and row query. |

[CRM read](../../../src/erp/crm/repositories/resources/reads.py) ·
[Finance](../../../src/erp/finance/service.py) ·
[Base](../../../src/erp/base/service.py) · [Sales](../../../src/erp/sales/service.py) ·
[Inventory](../../../src/erp/inventory/service.py) ·
[Reporting](../../../src/erp/reporting/service.py).

On 20 November, warm Production browser searches in Command Center had middle
times of 8.2 seconds for Contacts and 8.5 seconds for Leads, five samples each.
The ERP reopen took 45.3 seconds to display the first Contacts rows. A separate
API run after warm-up had 0 of 28 searches finish within 2 seconds.
PostgreSQL executed representative Contacts and Leads queries in 1.56 and
2.17 milliseconds on 500 Contacts and 431 Leads. These measurements identify a
large cost around the statement and say little about query plans at future
record volumes. Both factors need independent verification.

## 2. Decision and ownership

Use **one shared collection reader** inside the current ERP API for module
lists, searches, nested collections, and resource pickers. Install it on the
existing routes as they migrate. Use it from the first implementation of a
new collection route. A module supplies the records, query vocabulary and
permission rules. ERP supplies the request parser, authorization boundary,
page execution, response normalization and diagnostics.

| Owner and location | Responsibility |
| --- | --- |
| `api/erp/collections.py` | Register guarded GET routes with `collection_get` and provide the shared query parameter and filter-object parser. Module endpoints declare their own OpenAPI inputs and discovery. |
| `src/erp/collections.py` | Run an authorized resource definition. Build the filtered IDs, ordered page, exact total, and page projection. Submit a bounded governed SELECT and decode its result. |
| [Module admission](../../../src/erp/module_access/http.py) and [User Preferences](../../../src/erp/user_preferences/admission.py) | Bind the verified Environment, enforce activation and prerequisites, classify policy errors, and preserve the existing write guard. |
| The module's API and service | Own route URLs, capability resolver, typed filter model, scope predicates, joins and serialization. Only the owner adds indexes or changes search semantics. |
| Shared ERP frontend and module resource adapters | Map list and discovery requests to the Command Center SDK, use delegated transport, and keep module-specific wire adapters where needed. |

The core interface has two inputs. The normalized query is immutable and
contains search, typed filter values, ordering, page index and page size.
The resource definition is server-owned and contains the following.

| Required entry | What the owner provides |
| --- | --- |
| Resource, identity and source | Module key, resource key, public row identity, trusted MetaTables binding, and the authorized parent/related modules used by the query. |
| Permission and visibility | Existing capability resolver, required capability, caller-scoped predicates and, for nested routes, the predicate for a visible parent. |
| Filter model | Typed accepted values, defaults, scope, per-filter predicate, and which values may be advertised in discovery. |
| Search and order | Search predicate factory and match mode, allowlisted sort expressions, direction, null placement, and stable unique tie-breaker. |
| Projection | The current list fields and a query that yields one row per page ID. A pure formatter may turn typed values into the module's existing wire representation. |

A definition builds SQL expressions from bound arguments and verified request
context. Database name, table names, predicates and SQL operators come from
server-owned bindings. The reader checks the resource definition against the
selected DataSource once bindings are available. Domain-specific projections
reuse the owning models and services. A projection or formatter may use the
page data it was given and performs zero additional data calls.

## 3. HTTP and filter contract

### New and existing routes

New collections use the module prefix and a resource-owned `GET` route. Nested
collections use a typed parent path parameter. Keep detail routes and discovery
separate. Declare these inputs in OpenAPI even when a common parser handles them.

| Request argument | New route rule |
| --- | --- |
| `page_index` | Zero-based integer, default 0. Use the documented resource bound with a default maximum of 100,000. |
| `page_size` | Integer, default 25, range 1–100 or a smaller resource-specific upper bound. |
| `search` | Optional text. Trim surrounding whitespace, treat an empty search as omitted, and accept up to 200 characters by default. Document the matching mode. |
| `filters` | One URL-encoded JSON object, default `{}`. Reject duplicate keys, unknown keys, invalid types, and conflicting repeated parameters. |
| `ordering` | One declared key, with an optional leading `-` for descending. Omission selects the declared default. Every ordering ends with a stable unique identity. |

Legacy adapters preserve existing paths, parameter formats, bounds, sorting,
errors and response fields. For example, Finance uses the flat `state`
parameter and advertises no user-selectable order today. CRM Contacts already
accepts JSON `filters` and `ordering`. Inventory uses flat
`operating_company_uid`, `stock_item_uid`, `state`, and `include_archived`.
Each adapter maps its actual contract into the shared query without broadening
what the caller is allowed to read. Flat-query routes reuse the common FastAPI
page index, page size and search declarations. They retain their original
typed filter parameters and publish them in OpenAPI.
[Finance routes](../../../api/erp/finance/main.py) ·
[CRM query parser](../../../api/erp/crm/query.py) ·
[Inventory routes](../../../api/erp/inventory/main.py).

### Filter evaluation

The match rule is **record visibility AND parent scope AND search AND every
active filter**. A resource may search several fields with OR within its search
predicate. A declared array filter uses any-of membership unless its contract
explicitly defines all-of. Range semantics belong to the declared filter,
including units, inclusive or exclusive bounds, and date or time zone rules.
New timestamp range filters use a lower inclusive and upper exclusive bound by
default. Money uses the module's exact decimal type and currency rules.

- Omitted means use the resource default. A supplied `false` or `0` is a real
  value and reaches the predicate. New filters reject null, empty strings,
  and empty arrays unless the field explicitly gives them a meaning. A
  declared nullable-state filter uses an explicit value or operator.
- Bind untrusted values as parameters. Literal substring search escapes
  percent, underscore and the escape character; equality and prefix matching
  use the resource's declared normalization. A display label or Decimal string
  is sorted through its proper underlying type.
- Use a semi-join or `EXISTS` for many-to-many matching so the same authorized
  record counts once even when several children match. Use the same
  predicates for counts, page rows, and all-matching action selection.
- An access predicate remains mandatory even if a filter names another user,
  operating company, or parent. Such filters can narrow the authorized set.
  Actions re-evaluate the selection and their own permissions at preflight and
  execution. Pagination and presentation sort carry no selection authority.
- A recognized key with an invalid value produces the route's existing
  validation response. New routes use HTTP 422 and identify the field. A
  valid query with no matches returns HTTP 200 and zero items.

A resource schema test must compare each advertised filter and ordering key
with the accepted parser values. Test advertised enum options and any hidden
scope actually sent by the frontend. An accepted filter that affects the
response must compile to a tested predicate. Record legacy parameters that
currently have no effect for a resource variant, such as `state` on Inventory
Balances. Preserve the legacy behavior during migration and require an
explicit contract change to remove the parameter or give it new meaning.

## 4. Authorization, execution and response

### Move admission to the matched route

The current [ModuleAdmissionMiddleware](../../../src/erp/module_access/http.py)
runs before FastAPI matches the route. Adding a shared query under that
middleware would still pay for the policy-only SELECT on every request.

The shared GET registration marks its exact endpoint callable. Inside the
existing SDK identity, the middleware uses FastAPI's route matching, including
the effective paths of included routers, to resolve that callable. When it
recognizes the marked GET, it binds the verified Environment and requires the
collection statement to supply the admission decision before any successful
response. Unmarked routes keep eager admission and the existing request-scoped
`Admission`. This allows individual route migrations while protecting
neighboring writes, protocol routes and public-ingress registrations.
Verify actual mounted routes, including included routers, dynamic paths and
aliases.

For a collection, resolve the actor with the module's existing verified
caller or requester resolver. Resolve the Environment with
`scope_for_request` and the module and policy sources with the existing
bindings. The capability resolver runs once per request, with the module's
existing Team freshness rules. It must make its decision explicitly before
business rows are selected. Require this explicit capability decision even
when the reader performs its own module admission. If a legacy route
specifies that admission takes precedence over a validation or capability
error, use its existing policy-only check for that rejected request.

### Admit and read from the same snapshot

Use the existing `EnvironmentModuleActivation` row for the bound Environment.
Use [the module registry](../../../src/erp/modules.py) to derive the required
module closure and the valid prerequisite edges. The reader's policy subquery
performs the same checks as User Preferences. A policy must exist, have a
positive version and contain a unique array of known optional module keys
with all prerequisites. The effective set is the stored optional keys plus
required modules, intersected with provisioned modules. The required closure
must be contained in that set.

Use one policy decision builder in the module access package. In PostgreSQL, cast the
stored JSON to JSONB, inspect with `jsonb_typeof`, and expand array elements
with `jsonb_array_elements`. In SQLite, validate JSON before calling
`json_type` and use scalar `json_extract` on the bounded declared module
positions. This works under the local MetaTables authorizer. Give the reader
an empty array when the shape check fails and classify that policy as
invalid. Check that each member is a string and count distinct keys to
detect duplicates. Derive the prerequisite pairs from the registry and check
them against the same active-key set. Test both SQL forms against the existing
User Preferences decision with valid, invalid, missing, inactive, and
unprovisioned policy fixtures.

The selected policy columns are internal to the result decoder. The request
returns the existing `module_disabled` response on a valid policy that denies
access, and the existing policy-unavailable or source-mismatch response when
the policy is unusable. Only an allowed decision can produce a collection
response with business rows and a match count.

The policy and data bindings must resolve to the same governed DataSource.
A new query after an activation change commits sees that change. A read
already admitted against the previous snapshot may finish. Writes keep the
version and lock guarantees in [ADR 0001](0001-user-preferences-and-module-activation.md).
A source that cannot share the policy snapshot requires a reviewed separate
admission design satisfying that ADR before it is migrated.

### Reference query shape

Compile one parameterized SELECT with the installed MetaTables compiler and
submit it through `MetaTable.execute_operation`. The following is a template
for the generated statement. Module-specific expressions are in angle brackets.

```sql
WITH decision AS (
    SELECT <one row: allowed, disabled, or policy_unavailable>
),
visible_parent AS (
    SELECT <one flag for the parent scoped to the caller and decision>
),
matching AS (
    SELECT r.uid, <ordering expressions>
    FROM <registered resource> AS r
    JOIN decision AS d ON d.state = 'allowed'
    JOIN visible_parent AS parent ON parent.allowed
    WHERE <record visibility AND search AND filters>
),
total AS (
    SELECT count(*) AS total_items FROM matching
),
page AS (
    SELECT <matching identity and ordering columns>
    FROM matching
    ORDER BY <allowed keys and unique tie-breaker>
    LIMIT :page_size OFFSET :page_offset
),
projected AS (
    SELECT <one wire row per page ID, plus ordering columns>
    FROM page
    JOIN <owner tables needed by the list projection>
)
SELECT decision.state, visible_parent.allowed AS parent_allowed,
       total.total_items, projected.*
FROM decision CROSS JOIN visible_parent CROSS JOIN total
LEFT JOIN projected ON TRUE
ORDER BY <same page ordering>;
```

For top-level routes the parent subquery yields true. For a nested route it
checks parent visibility before selecting child records. If the parent is
unavailable, preserve the domain's existing denial or 404. Encode the internal
result as typed page rows plus metadata. The left join emits a single sentinel
with a null row identity for an empty page, including a past-end page with a
nonzero total. The decoder discards that sentinel and computes `hasNextPage`
from the requested page and exact total. It preserves the route's declared
previous-page behavior. Internal policy, parent and ordering columns stay
inside the reader.

The page is at most the configured page size, even with one-to-many joins.
Aggregate child rows set-wise or project the display fields alone as the
existing route contract permits. Preserve the complete field where the
existing response promises it. Preserve row types and order across PostgreSQL
and SQLite, with a compatibility serializer for existing envelopes. Count the actual MetaTables
HTTP data requests in verification, including SDK continuation. A normal
warm collection uses one data request with a bounded response and timeout.
Readiness, verified identity and Team lookups are tracked separately.

## 5. Worked migrations

### Finance invoices, status filter plus search

The current Finance endpoint accepts this request.

`GET /api/finance/v1/invoices/?page_index=0&page_size=2&search=acme&state=posted`

Normalize to search `acme`, filter `state = posted`, and page `0/2`.
Require `finance.read`. Match `state = posted AND (name contains 'acme' OR
party_name contains 'acme')`, subject to Finance visibility. Use
`created_at DESC, uid ASC` as today. Preserve the invoice projection,
including decimal strings. Keep `draft`, `posted`, and `void` in discovery;
`state=paid` remains invalid.

| Fixture row, newest first | Reference | Party name | State | In matching set |
| --- | --- | --- | --- | --- |
| A | ACME-003 | North | draft | No |
| B | ACME-002 | North | posted | Yes |
| C | INV-028 | Acme Services | posted | Yes |
| D | INV-029 | North | posted | No |
| E | ACME-001 | North | posted | Yes |

Page 0 returns B and C with `totalItems=3` and `hasNextPage=true`. Page 1
returns E with the same total. Page 2 returns an empty list with the same
total. The count and each page use one SELECT each. Use the same reader for
`/invoices/{uid}/allocations/`. Put the visible invoice check and allocation
count/page into that statement, preserving a 404 for an unavailable invoice
and an empty 200 for a visible invoice with no allocations.

### Inventory balances, related-row filtering and projection

For `GET /api/inventory/v1/balances/`, keep the current flat
`operating_company_uid`, `stock_item_uid`, and `search` contract. Require
`inventory.read`. Bind `stock_item_uid` against the balance. For the company
filter and text search, match the linked stock item by its operating company
and name before counting or paging. Preserve the current created-at and UID
order. After selecting the page, join stock items and locations once for their
names, unit, currency and conversion increment. Reuse the current pure
Decimal calculations for on-hand, reserved, available and cost in the row
formatter. Preserve the current missing-link error instead of dropping an
orphaned page row through an inner join. A full 25-row page and an empty page
must each use one governed data request.

### CRM Contacts and Reporting, boolean filters and row visibility

Contacts accepts `filters={"archived":false,"has_open_tasks":false}`. The two
predicates are active-only contacts and absence of a task whose completion
and archive timestamps are both null. When a search term is present all three
predicates apply together. The `tag_uid` filter remains an existence test.
Keep the current default last-seen sort and null and UID ordering. Check
equivalence on both legacy CRM storage and the Base-adopting path before
switching the route.
[CRM filters](../../../src/erp/crm/models/queries.py) ·
[CRM current predicates](../../../src/erp/crm/repositories/resources/reads.py).

Reporting must always include `created_by_uid = verified_actor_uid` in
matching, including when search and state are omitted. Seed two reports with
the same name and state under different owners. Each caller must get only
their own row and a total of one. A response with one row and a total of two
fails the authorization test.

## 6. Frontend, indexing, and budgets

- Keep discovery on the Command Center SDK's separate discovery boundary.
  The adapter sends semantic search, filters and declared hidden scope when
  the resource uses them. A static discovery response can be reused for the
  same resource, verified caller, Environment and application session.
  Dynamic discovery uses its actual semantic inputs as part of its cache key.
  Clear discovery and in-flight reads on a caller, Environment or relevant
  policy change. Keep fresh API authorization on every collection read.
- The shared adapter forwards cancellation, resets to the first page when
  search, filters or sort change, and drops a response superseded by a later
  query. Changing pages reuses discovery when its semantic inputs are
  unchanged. Module landing routes start the first authorized page alongside
  independent startup work. Measure visible rows, including rendering.
- Use the declared SDK contracts
  `command-center.resource_collection@v1` and
  `command-center.resource_discovery@v1`, with the pinned frontend package's
  manifest and its fixture registry. Validate the normalized adapter result
  for legacy envelopes and the serialized HTTP body for direct conformance.

### Cardinality and index selection

For each resource, use a populated PostgreSQL fixture at expected peak and
growth volumes. Record the existing physical indexes from `pg_indexes`,
refresh fixture statistics with `ANALYZE`, and capture the following evidence.

| Measure | Record |
| --- | --- |
| Table and filter cardinality | Base-table row count, rows visible to representative callers, distinct values, null fraction, and frequencies of common and rare values for permission, filter, and join keys. Use `pg_stats` and scoped aggregate counts. |
| Selectivity of the actual query | Matching authorized IDs and their share of visible rows for common, rare, and zero-match terms or filter values. Measure frequent combinations together, such as owner plus status or stock item plus operating company. |
| Join cardinality | Number of related rows per base record, including typical and high-fan-out records. For a relationship predicate, count the matching base IDs and verify the join leaves the total and page semantics intact. |
| Planner accuracy and work | Run `EXPLAIN (ANALYZE, BUFFERS)` on the actual parameterized statement, including the permission scope and exact count. Compare estimated and actual rows at scans and joins, and inspect loops, rows removed by filters, buffer usage, sort spills, and execution time. Cover the first page and a deep page. |

When estimates differ substantially from actual row counts, check whether the
fixture represents skew and correlations between filters, and whether its
statistics reflect the loaded data. Use the same data and query parameters
for the baseline and each candidate.

Choose candidates for the measured predicate and ordering. Test a composite
B-tree with the equality scope or filters as leading keys and range or sort
keys next where that matches the workload. Verify the actual ordering,
including mixed directions and the unique tie-breaker. Check the plan
without optional filters too. Use a partial index only when PostgreSQL can
infer its predicate from the submitted query. For literal substring queries,
test a trigram index on the exact normalized expression used in the predicate.
Check selective, common and two-character terms, since a pattern with no
extractable trigrams can still scan the full index.
[PostgreSQL statistics](https://www.postgresql.org/docs/current/view-pg-stats.html) ·
[Reading query plans](https://www.postgresql.org/docs/current/using-explain.html) ·
[Multicolumn indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html) ·
[Partial indexes](https://www.postgresql.org/docs/current/indexes-partial.html) ·
[Trigram index support](https://www.postgresql.org/docs/current/pgtrgm.html#PGTRGM-INDEX)

**Worked index decision for Finance invoices.** Imagine 100,000 visible
invoices with 90,000 posted, 9,900 draft, and 100 void. This is an illustrative
fixture. Three distinct states still produce very different selectivity.
Start with the existing `ix_erp_finance__invoice_state` and compare it against
`(state, created_at DESC, uid ASC)` for the status filter and that route's
ordering. Run the posted, void, and unfiltered cases. For the unfiltered case,
benchmark `(created_at DESC, uid ASC)` separately if sorting is expensive.
Compare the page and count work for each case. An index that speeds up the
first page may still leave the exact count as the main cost for the posted
filter. [Finance migration](../../../src/erp/finance/migrations/versions/erp_finance/0001_create_finance_invoices_payments_.py) ·
[Finance collection](../../../src/erp/finance/service.py)

Keep the before and after plans with the resource's verification record.
Record the chosen index or the evidence for keeping the existing set, and
check index size and representative insert/update cost before promoting a
new index. Own new indexes in the module's Alembic provider.

### Timing and acceptance

- Shared MetaTables latency needs a separate trace. Record ERP identity and
  capability timing, the governed call's connection setup and first response
  byte, and SQL time. The installed transport creates a new HTTP session for
  a data call. Compare fresh and reused authenticated connections on the same
  route before changing its SDK transport. Preserve timeouts, credential
  scoping and retry behavior. Use safe stage names and request IDs; keep
  business data and raw query terms out of timing records.

The acceptance target is **95 of 100 warm searches or filter changes within
2 seconds from input to updated results**, including empty results. Compare
against actual populated collections in Command Center. Budget at most
1 second for the warm governed call as an engineering starting point; revise
the budget from measured stage traces. ERP reopen to visible first rows targets
10 seconds with the API running. Report runtime wake-up separately.

## 7. Implementation order and required evidence

| Increment | Deliverable and verification |
| --- | --- |
| 1. Shared execution and registration | Add the route wrapper, definition and reader. Test the actual shared ERP FastAPI entrypoint, early auth errors, and the existing admission of sibling routes and writes. Run against a verified ready local MetaTables SQLite DataSource. |
| 2. First cross-module change | Migrate Base parties, CRM Contacts and Leads, Finance invoices and allocations, and Inventory balances and movements. Verify the cases in section 5 and both CRM storage paths. Migrate Reporting's owner-scoped lists before using the pattern as the default for new collections. |
| 3. Remaining surface | Inventory the mounted routes and resource variants for Catalog, Sales, Projects, People, Collaboration, Marketing, Purchasing, Manufacturing, Commerce and remaining collections in the first modules. Include child lists, pickers, and other collection-shaped responses in the inventory. Record owner, route, filters, sort, projection, policy dependency, DataSource, and observed calls. Track each route as legacy or migrated. |
| 4. Production promotion | After local verification and explicit deployment approval, verify the deployed API before promoting the frontend. Run the same signed Command Center scenarios on an approved populated environment and on the active Production collection. Publish the volumes, stage timings and sample counts separately from the release status. |

Each migration adds evidence at the existing integration points.

- [Module admission tests](../../../tests/erp/test_module_access.py).
  Exercise the SDK-authenticated local caller and the hosted signed-assertion
  contract, forged scope, inactive module, unprovisioned
  module, invalid or missing policy and a mismatched source. Use two API
  instances against the same local DataSource. Commit deactivation in one and
  assert the next collection through the second returns 403. Assert a protected
  mutation and an unrelated legacy route still use their original admission.
- [CRM collection tests](../../../tests/erp/crm/integration/test_resource_collections.py).
  Reuse the private PostgreSQL fixture pattern for actual query plans and the
  existing operation-capture tests for bounded SQL. Cover duplicate related
  matches, null sort values, ties, deep and past-end pages, and an exact total
  under a restricted actor. Record separate run results for captured SQL,
  actual PostgreSQL execution, and real SDK-authenticated API calls.
- [Finance tests](../../../tests/erp/finance/test_local_finance.py) and
  [Inventory tests](../../../tests/erp/inventory/test_local_inventory.py).
  Assert request counts at the MetaTables boundary for 0, 1, 25 and the
  maximum supported number of returned rows. Verify Money and Inventory
  decimal representations, child lists, missing related rows, and matching
  by a joined field. Assert that empty and fully populated pages both pass
  the same call-count budget.
- **Populated benchmark.** Use the fixture, query cases, and before and after
  plans in [Cardinality and index selection](#cardinality-and-index-selection).
  Take 100 sequential browser trials with a repeatable mix of those cases.
  Run a separate concurrent workload at the module's agreed operating load.
  Publish warm search, ERP reopen, and cold API admission independently.

Use the normal repository checks and version-matched contract fixtures before
promotion. Apply new indexes through module-owned migration providers. Keep
those index revisions additive so the previously verified API and frontend
pair can be restored if a rollout regresses behavior.
