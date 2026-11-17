# ADR 0001: Source-linked reports and controlled local refresh automation

Accepted for local implementation, 17 November 2026, after the recorded OpenERP review.
API extension only; no Agents/MCP. Reporting owns Definition, Run, RunStep, Schedule and
AuditEvent in erp-reporting with independent metadata, provider/history/version table.
All business owners are lazy optional dependencies. No foreign models or direct joins.
Public read ports expose only owner-authorized collection/get and source identity; each
port uses that owner's verified caller policy and read-only capabilities. Same governed
source is required in this first release. Reporting never writes another owner's data.

Definitions are creator-private, active/archived, versioned name/kind/search. Two fixed
kinds: commercial (confirmed Sales orders and posted customer Finance invoices) and
operations (Projects, Inventory movements, Purchasing orders, Manufacturing production).
A shared search phrase narrows each owner's documented collection. At most 200 matching
source rows per owner, fetched in bounded pages; exceeding the bound fails the step
explicitly. Preserve whitelist fields, source UID/version/path and capture time. Counts
and totals reconcile to retained rows; exact Decimal sums never mix companies/currencies.
Commercial link checks use Finance's Sales source identity; mismatched/out-of-scope links
are visible. Net orders, invoice net/gross, allocated and remaining are separate measures.
Operations counts group by owner/status. No silent source omission or truncated total.

Each run freezes definition/version/search and ordered source steps. Stages read source
records at their own capture time; label the result as a rolling capture window, not an
atomic cross-module or historical accounting snapshot. Results remain immutable after
success. Rechecking source versions reports unchanged/changed/missing counts and links;
current owner read authority is required for every result read, row collection, CSV and
verification. Metadata/progress remain creator-private. CSV escapes spreadsheet formula
prefixes; result data renders as text. Cross-user sharing is deferred.

Manual run creation uses original request UUID. Run states queued/running/failed/
succeeded/cancelled; steps pending/running/failed/done. Execute one owner step at a time
under an atomic version and random lease-token claim with a two-minute expiry. Commit
output/progress/audit only under the same lease and versions. Cancellation invalidates
in-flight workers. A killed worker leaves visible running state; after expiry, explicit
recovery returns the current step to pending. Failed steps require explicit retry and
retain completed earlier steps; no implicit write replay. Safe failure codes/messages
are persisted without raw transport payloads or credentials. Original-UUID lookup
resolves uncertain creation; reload resolves uncertain transition/worker responses.

Schedules are creator-private, active/paused, linked to an active definition, with a
fixed 1–1440 minute interval and UTC next due time. Create paused; activate queues the
first execution on the next worker tick. A guarded due claim advances next due and
creates one deterministic scheduled run and steps atomically. No catch-up burst and
no overlap while the same schedule has queued/running work. Pausing stops future runs;
already queued work can be cancelled separately. Archived definitions pause due schedules
with a retained reason. Schedule creation/changes require reporting.manage; runs require
reporting.run; definitions require reporting.write; reads require reporting.read. Every
mutation also enforces creator identity and optimistic versions, including local mode.

A separate loopback-only worker calls the authenticated local Reporting tick endpoint;
it works only as the current SDK user, never an injected stored execution identity.
Each tick queues at most one due schedule and advances at most one step. It never retries
failed/expired runs automatically. An in-process per-caller heartbeat reports the last
actual tick and becomes unavailable after 30 seconds/restart; UI shows that scheduled
work requires this running local worker. No timer/migration runs inside API startup.
No platform scheduler/resource is activated. Hosted worker identity/delegation and
release policies require a separate approved deployment verification.

Private /api/reporting/v1 provides own readiness, typed definition/run/schedule
collections and discovery, detail/audit, run queue/advance/retry/recover/cancel, result
summary/rows/CSV/source verification, schedule activate/pause and local worker status/tick.
Companion frontend owns Saved reports, Report runs and Schedules in the shared left
navigation, source drill-down, progress and recovery controls, independent startup,
standard dirty/stale/uncertain behavior and same-artifact guides in General → Modules.

Evidence: fresh/repeated own migration, source reconciliation/exact money/bounds,
creator and owner authorization, absent owners, races/late rollback, lease expiry and
restart, cancellation/retry, deterministic due scheduling and real local worker,
HTTP contracts, optional import isolation, companion browser flow, six viewports/themes,
shared docs and full ERP regression. Local mode and exact ready SQLite source are
mandatory. No push/tag/hosted migration/deployment before explicit user approval.
