# ADR 0001 — Independent Marketing mailing API

Accepted for local implementation, 17 November 2026, after the
[functionality review](../openerp-coverage.md). API extension only; no new Agents/MCP.

## Ownership and prerequisites

Marketing owns Subscriber, Mailing, Recipient, DeliveryEvent and AuditEvent, own
SQLAlchemy metadata, `erp-marketing` namespace, explicit provider/model registry,
0001 initial history and `erp_marketing__alembic_version`. Base is the sole business
prerequisite. Optional CRM read integration is lazy, local and separately disableable.
Use existing authenticated identities/capabilities; no login or role database.

Subscriber binds an immutable active Base person and normalized email. Email is
unique globally to prevent duplicate recipient delivery; identity/email changes need
a new explicitly consented subscription. Subscription and unsubscription require
an evidence/reason note, retain actor/time audit and fence positive versions. This
is operational evidence, not an assertion of legal compliance. Existing recipients
retain their trace after unsubscribe. The owner policy checks Base access for choice
and verification; Marketing records have their own authorized reader audience.

## Mailing and local delivery

Mailing has name/subject/plain-text body/source label, immutable delivery mode
`local_capture`, and draft → queued → completed or draft/queued → cancelled.
Only draft content and audience can change. Draft recipients are unique per mailing
and subscriber; explicit remove is supported while draft. Queue requires reviewed
nonempty content and at least one subscribed recipient. A boolean acknowledgement
confirms the local capture boundary; no generic external provider URL is accepted.

Capture runs only after verifying actual Local SQLite and the exact owning source.
Each explicit request processes at most 10 pending recipients (32 governed statements including fences and audit). A transaction fences
Mailing, every referenced Subscriber and affected Recipient, captures immutable
subject/body/address for eligible members, and records suppressed outcomes for
unsubscribed members. This serializes capture with unsubscribe and concurrent runs.
The parent version and pending states prevent duplicate capture. A batch failure
rolls back all payloads/events/audit. Queued data is resumable after restart; read
state before retrying an uncertain batch. Completed is reached only when no pending
recipients remain. Cancellation marks remaining pending recipients cancelled in a
bounded, versioned operation; cap draft audiences at 100 to bound that transaction.

Recipient records carry capture/suppression/cancellation state, captured payload,
immutable simulated engagement events and optional existing CRM task link. No real
`sent` or `delivered` claim is allowed. Simulate opened/clicked/replied/bounced only
for captured recipients, with explicit evidence and stable unique event kind per
recipient. A bounce cannot coexist with positive engagement; later positive events
cannot follow a bounce. Metrics report local captures, suppressions and explicitly
simulated engagement, never inbox delivery. No live network send exists.

## Public contracts and integrations

`/api/marketing/v1` owns readiness, SDK discovery/collections, Subscriber/Mailing
CRUD with strict typed payloads, subscription actions, recipient add/remove/list,
queue/capture/cancel, recipient detail/events, simulation and follow-up linking.
Create requests use UUID identity for reconciliation; other mutations use expected
versions and never promise blanket replay. Parent and child versions fence changes.
Capabilities `marketing.read/write/manage/configure`; manage queues/runs/cancels,
simulates outcomes and links follow-ups. Base public read contracts supply person
choices. Unknown fields and supplied identities fail validation.

Optional CRM linking reads a task and its Contact through CRM's public API, verifies
active state and matching Base consumer identity, then stores only its UID/reference
on the recipient. This is a link to existing work, not automatic task creation.
Require an explicit recorded reply outcome for this local handoff; display that the
reply is simulated. Never copy CRM email or task-graph state. No remote endpoint or
credential forwarding is invented; hosted transport requires a later approved design.

## Local cycle and release

First review/scaffold/apply only this provider on the verified source, test standalone
Base prerequisites and disabled CRM, permissions, dedupe, snapshot/eligibility,
unsubscribe/capture races, batching/restart, rollback, outcome rules and optional
CRM link mismatch/unavailability. Use owned actual local fixtures and authenticated
HTTP; distinguish policy fixtures and simulated engagement from real evidence.
Companion Marketing screens and guides live in the single ERP site, with shared
General → Modules navigation. Browser, startup, recovery, theme/responsive, docs and
combined build pass before Inventory starts. Prepare only an inactive `-marketing`
workflow with own migration Job. All hosted deployment/push/tag/reconciliation and
external-message provider activation remain pending explicit user approval.
