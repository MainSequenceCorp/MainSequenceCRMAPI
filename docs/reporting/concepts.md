# Concepts

A creator-private Definition selects commercial reconciliation or operations status
and a literal source search. A Run freezes that configuration/version, with one
RunStep per owner. Schedule belongs to a Definition and queues deterministic due runs.
AuditEvent records actor, action, version and changed field names, never credentials.
Five tables, separate erp-reporting namespace/metadata and erp_reporting__alembic_version.

Commercial reads confirmed Sales orders and posted customer Finance invoices. Exact
Decimal totals group by company UID and currency UID; order net, invoice net/gross,
allocated and remaining are independent measures. Invoice source links are matched,
unlinked, outside capture or mismatched. Operations reads Projects projects, Inventory
movements, Purchasing orders and Manufacturing production; counts group by source/state.
Public owner collection/get methods enforce each owner's read policy. Same governed
source is required. Source adapters expose no mutation capability or foreign models.

At most 200 matching rows per owner (including the Finance pre-type-filter collection).
Two bounded pages must reconcile count/unique IDs; changes that break those checks fail
the step. This is a rolling capture window, not a cross-module transaction or historical
accounting snapshot. Captured records retain original UID/version/time/path. Successful
results are immutable; source verification rechecks captured versions and missing rows,
not newly added records. Fresh runs discover new records. CSV neutralizes formula prefixes.

States: queued → running → succeeded, with failed and cancelled terminal branches.
A version-fenced random UUID claim expires after two minutes. Output commits only with
the same actor, run/step versions, lease and unexpired deadline. Cancellation invalidates
claims. Explicit retry retains completed sources; explicit recovery resets an expired
source to pending. No automatic retry of failed or expired work. Original request UUID
resolves uncertain creation; inspect current state before retrying uncertain transitions.

Schedules start paused. Activation makes first execution immediately due, then fixed
1–1440 minute intervals apply. Guarded next-due update plus deterministic run and steps
commit atomically. No overlap with queued/running work, no missed-run burst. Archiving
a definition prevents new runs and pauses due schedules with a reason. Pausing alone
does not cancel existing work. Each worker tick queues at most one due run and advances
one source. The local worker acts as the verified currently signed-in SDK user only.
Its process-local per-user heartbeat expires after 30 seconds; status is not a job guarantee.

Capabilities: reporting.read for all operations; reporting.write edits definitions;
reporting.run queues/advances/recovers/cancels; reporting.manage manages schedules/ticks.
All records remain creator-private. Every result, row collection, CSV and source check
revalidates all source permissions. Missing owners fail explicitly. Environment flags
REPORTING_<OWNER>_ENABLED=false disable a lazy source without importing it.

Deferred: arbitrary SQL/code/formulas, PDF/QWeb, FX/statutory accounting, shared reports,
record-change hooks, notifications/webhooks, hosted worker execution identity and Agents/MCP.
Future expansions belong to a later reviewed API ADR/release; no full OpenERP parity claim.
