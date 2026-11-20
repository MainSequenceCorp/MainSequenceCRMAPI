# ADR 0007 · Local ERP collection verification

## Collection coverage

The shared reader returns the exact count and requested page from the same
filtered IDs. Related fields needed only for display are projected after
pagination. The same governed SELECT evaluates module admission for a
route registered with `collection_get`.

| Module | Shared reader coverage | Admission or data boundary |
| --- | --- | --- |
| Base | Business Directory resource lists | Base is required. There is no optional-module activation SELECT. |
| Catalog | Item and reference resource lists through the generated routes | Same statement |
| CRM | Core lists, email messages, versioned records, and Solution Selling resources including Leads | Same statement. Hosted legacy PostgreSQL queries use the shared admission decision around their existing single-statement payload. |
| Sales | Orders | Same statement |
| Finance | Invoices, payments, allocations, and inventory valuations | Same statement, including the parent check on allocations |
| Projects | Projects, tasks, and a task's time entries | Same statement, including the parent check |
| People | Primary collections, including employee-scoped lists | Same statement |
| Collaboration | Discussions, messages, revisions, and paged audit | Eager admission and owner checks for project-scoped discussions. Count and page share a query after those checks. |
| Marketing | Subscribers, mailings, recipients, delivery events, and paged audit | Same statement, including the parent check on child routes |
| Inventory | Stock items, locations, balances, movements, and paged audit | Same statement, including related data for balances and movement entries |
| Purchasing | Orders | Same statement |
| Manufacturing | Primary resource lists | Same statement |
| Commerce | Primary resource lists | Same statement |
| Reporting | Definitions, schedules, and runs | Same statement with the caller's ownership restriction |

CRM campaign sequences, contact affiliations, transfer lists, and owner
pickers keep their existing routes and read implementations. Some produce a
different envelope or read through an owning service. Reporting run rows page
an immutable stored result. Fixed-size audit feeds keep their bounded
response. Those surfaces are outside the single-statement results below.

## PostgreSQL fixture and results

Ran 56 cases on disposable PostgreSQL 16 with the collection SELECTs generated
by the service code, 100,000 rows per sampled business table, and a page size
of 25. Loaded deterministic synthetic values, recreated the modeled
nonunique indexes and identity keys, and ran `ANALYZE`. Each case recorded
the returned page size and exact total alongside
`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`. The figures are one execution of
each case on that fixture. They include SQL admission where applicable and
exclude HTTP, SDK, and browser work.

| Sampled collection | Common exact matches | Common SQL ms | Rare exact matches | Rare SQL ms | Miss SQL ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Base parties | 10,000 | 31.30 | 1 | 18.25 | 17.84 |
| Catalog items | 10,000 | 44.19 | 1 | 33.25 | 31.56 |
| CRM contacts, portable query | 10,000 | 21.42 | 1 | 19.28 | 18.69 |
| Sales orders | 10,000 | 17.16 | 1 | 16.25 | 14.49 |
| Finance invoices | 10,000 | 17.98 | 1 | 16.14 | 15.36 |
| Projects | 10,000 | 41.51 | 1 | 28.79 | 26.58 |
| People employees | 10,000 | 28.18 | 1 | 16.05 | 16.08 |
| Collaboration discussions | 10,000 | 42.24 | 1 | 35.51 | 30.77 |
| Marketing subscribers | 10,000 | 35.77 | 1 | 25.91 | 23.82 |
| Inventory balances | 10,000 | 34.88 | 40 | 13.87 | 11.52 |
| Purchasing orders | 10,000 | 17.06 | 1 | 15.97 | 15.89 |
| Manufacturing bills of materials | 10,000 | 26.38 | 1 | 15.00 | 14.27 |
| Commerce sites | 10,000 | 25.10 | 1 | 14.82 | 15.39 |
| Reporting definitions, owner-scoped | 5,000 | 11.57 | 1 | 4.80 | 4.81 |

### Cardinality, plans, and index decisions

- **Finance state.** The table had three distinct non-null states and
  100,000 visible invoices. Exact counts were 90,000 posted, 9,900 draft,
  and 100 void. The existing `ix_erp_finance__invoice_state` estimated 110
  void rows, read 100, and served the first page in 0.80 ms. For posted,
  the sequential scan estimated 90,097, read 90,000, and removed 10,000
  rows. The full statement took 52.58 ms. The unfiltered exact count plus
  page took 56.40 ms. A candidate B-tree on
  `(state, created_at DESC, uid ASC)` was used for the void deep page
  (offset 75). The matching scan used five cached blocks, compared with
  102 for the existing state index, and execution took 0.41 ms versus
  0.48 ms. The candidate also enabled index-only scans for the broad
  posted and unfiltered matches.
- **Finance substring.** Tested GIN trigram indexes on the exact
  expressions `lower(name)` and `lower(party_name)`. The rare match
  went from 16.14 ms to 0.59 ms and the miss from 15.36 ms to 0.36 ms.
  The rare indexed heap scan estimated 20 rows and returned one. The
  common term matched 10,000 rows. Its candidate bitmap heap scan
  estimated 17,355, read 10,000, and the whole statement took 32.98 ms
  versus 17.98 ms in the baseline run. A two-character term returned one
  row, taking 35.09 ms baseline and 25.53 ms with candidate indexes
  installed. These samples do not isolate the cache effect or establish a
  production workload benefit.
- **Inventory join.** All 100,000 balances had a stock item. They referenced
  2,500 distinct stock keys, with 40 balances per referenced key. The rare
  item name matched just one referenced stock item and returned an exact
  total of 40 balances. Adding the stock-item and operating-company filters
  kept the same total and brought execution from 13.87 ms to 0.55 ms. The
  plan used the stock item's primary key and the existing balance stock-item
  index, with 40 estimated and 40 actual balances. Projection looked up
  related fields for the 25 selected rows.
- **Reporting visibility.** One fixture caller could see 25,000 definitions
  and the common term matched 5,000 of them. The existing creator index
  narrowed the read before the text predicate. The heap scan estimated 40
  matches and returned 5,000, removing 20,000 rows by filter. The query
  still took 11.57 ms. Real creator distributions and term correlations
  deserve a repeat check before changing indexes here.

Repeated the seven Finance cases five times per configuration on the same
fixture. Dropped the first pass per configuration. The candidate configuration
installed the composite B-tree and both GIN indexes. Execution times are
medians in milliseconds.

| Finance case | Existing indexes | Candidate indexes |
| --- | ---: | ---: |
| Rare term | 20.46 | 0.49 |
| Zero matches | 19.27 | 0.34 |
| Common term | 23.49 | 13.27 |
| Two-character term | 38.11 | 38.86 |
| Posted state | 58.80 | 37.40 |
| Void state, offset 75 | 0.49 | 0.43 |
| No filter | 67.44 | 39.65 |

Retain the existing indexes for this change. The candidate indexes save
tens of milliseconds on this data, and the broad totals still require
counting all matching IDs. Revisit candidates with production-shaped record
widths, observed selectivity, higher growth volumes, concurrent traffic,
and index write costs. The benchmark sampled one list per module plus
deeper and compound Finance or Inventory cases. Every resource and
conditional workflow still needs its own peak and growth evidence before
its index set is changed.

## Local application checks

- Verified the SQLite runtime was ready and bound to the expected disposable
  DataSource before applying migrations or running checks. A real local
  identity exercised all 14 modules through the shared API. In the warm
  search fixture each ordinary guarded route submitted one governed
  operation for policy, exact count, and page. Collaboration used its eager
  owner-check path. Separate API instances exercised policy deactivation.
  The same tests covered duplicate and missing policies, an unprovisioned
  module, missing parents, and the collection's safe `Server-Timing` stage.
- Ran the hosted CRM admission statement directly on the disposable
  PostgreSQL fixture. An active policy exposed the fixture result. Inactive,
  duplicate-member, and missing policies returned their admission decisions
  without a result payload.
- Ran the populated CRM collection and email suites on disposable
  PostgreSQL. They passed 63 and 17 tests respectively, including exact
  totals, stable ordering, nested visible fields, permission rechecks,
  and the pinned email collection and discovery schemas.
- The final backend regression run passed 250 tests with two skips. The
  ordinary API pre-push test selection passed all 25 tests.
- The frontend TypeScript check, 11 frontend test files, Vite production
  build, and strict MkDocs build passed.

Command Center’s input-to-visible-results and ERP reopen targets still
require measurement against the released API and frontend. This local check
does not include platform HTTP latency or a Production deployment.
