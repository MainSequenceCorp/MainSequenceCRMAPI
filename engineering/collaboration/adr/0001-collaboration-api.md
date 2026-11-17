# ADR 0001 — Independent Collaboration API

Accepted for local implementation, 17 November 2026, after the
[OpenERP review](../openerp-coverage.md). API extension only; no Agents/MCP.

## Ownership and audience

Collaboration owns Discussion, Message, MessageRevision and AuditEvent with one
`erp-collaboration` namespace, explicit model registry/provider and
`erp_collaboration__alembic_version`. Standalone operation requires no business module.
Platform-injected identity supplies actors; no login/role store is created. Optional
Projects integration is lazy and uses only its public read/permission contracts.

A discussion has immutable scope: shared, or one Projects project. Shared discussions
are visible to every authorized Collaboration reader; no private audience is offered.
Project discussions require Collaboration read AND current owner permission to read
that exact project. Posting/editing also requires Projects write. No subject, body,
history, audit, count or collection may bypass that owner check. Lost record access
removes access to all linked content, even for its creator/Collaboration manager.

To avoid collection/count leaks, the default collection includes ONLY shared
threads. Linked collections require one explicit `project_uid`, checked through the
owner BEFORE count/search/page; no mixed all-project collection. Direct thread/message/
revision/audit access rechecks its owner. Scope cannot change after creation, so
linked content cannot silently become shared. The UI states the chosen audience.

## Commands and history

`/api/collaboration/v1` provides normalized discussion discovery/collections/details,
create/edit, explicit close/reopen/archive/restore, paged messages and restricted
revisions, create/edit/retract messages and audit. Thread create acknowledges an
exact audience literal matching its scope. Request UUIDs identify creates and allow
GET-based uncertainty recovery, not command replay. Updates require positive integer
expected versions. All payloads forbid unknown fields and supplied actor identities.

Collaboration read permits visible content; write permits discussion creation, own
open discussion edits and messages in visible open threads; manage permits lifecycle,
thread editing and message retraction. Only the message author can edit its text;
author/manager may retract with a reason. Every content mutation fences/increments
the discussion version, preventing races with closure/archive; message updates also
fence message version. A monotonic thread sequence orders messages. Every initial,
edited or retracted version gets an immutable revision in the same transaction.
Normal reads hide retracted text; prior revision bodies are visible only to author
or manager, still under record-owner checks. Closed/archived threads freeze content;
manager reopens/restores before further work. Audit is permission checked and atomic.

No external delivery, private messaging, attachments, unread receipts, subscriptions,
realtime transport, CRM mail migration or generic task engine is included. Explicitly
retain CRM source provenance and existing audience rules.

## Verification and rollout

Use only exact ready MetaTables Local SQLite for own migrations, fixtures and first
API deployment. No startup migration. Verify fresh-process independence/restart,
owner gating including collections/counts and revoked access, strict SDK contracts,
concurrent posts/close, edit/retraction history, atomic failures and uncertainty.
Companion Collaboration pages and user guides join the one ERP/static-help site;
General precedes Modules everywhere. Local browser, responsive, theme, accessibility,
build and docs checks close the stage before Marketing. Inactive module-specific
`-collaboration` workflow/migration Job is prepared outside active workflows. Hosted
Team/storage/owner grants, production concurrency, bindings and all deployment-triggering
actions remain gated on explicit user approval after local evidence.
