# Email history API

**Status: implemented locally; deployment and live verification pending.**
The accepted [ADR 0002](../google_workspace_module/adrs/0002-selected-email-history.md)
workflow supports selected historical batches and explicit Lead associations.
Private/team visibility and an unattended worker are outside this release.

All core routes use the verified effective caller. `GET` requires `crm.read`.
Manual creation additionally requires `crm.create`. Provider operations are mounted
only with Google Workspace enabled and require `crm.transfer.import` plus read.
Import additionally needs create; enabling/refreshing sync also needs edit. Only
the source mailbox owner can change or refresh its thread selection.

`crm.read` admits shared saved history, including bodies, across the authorised
CRM instance; the importing actor is provenance and source-sync authority, not a
read-visibility restriction. All list/detail/search/MCP reads use this same policy.
Only the connected owner can search/preview/import from their Gmail account.
Import must explicitly describe the shared audience; Gmail source access is
never granted to other users by an email record or its original URL.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/api/crm/v1/email-messages/` | Metadata collection with authoritative `items`/`pageInfo`; bodies are excluded. |
| GET | `/api/crm/v1/email-messages/discovery/` | Canonical resource discovery, no bulk actions. Rejects page/sort presentation parameters. |
| POST | `/api/crm/v1/email-messages/` | Manually record email; source provenance is server assigned. |
| GET | `/api/crm/v1/email-messages/{uid}/` | Body, addresses, provenance, CRM links, thread selection/version and open follow-up. |
| POST | `/api/crm/v1/email-messages/{uid}/follow-up/` | Create/reuse open Task, optionally update its Contact's Lead next action atomically. |
| POST | `/extensions/google/email-search/` | Bounded metadata-only Gmail query; stores nothing. |
| POST | `/extensions/google/email-previews/` | Review one message; returns content and actor/account-bound 15-minute preview token containing only identity/hash. |
| POST | `/extensions/google/email-imports/` | Re-fetch and verify the reviewed content; save exactly that email. Never enables sync. |
| POST | `/extensions/google/email-conversation-previews/` | Review a bounded page for exact CRM context. Returns items, review_token, total_messages, next_offset and audience; saves nothing. |
| POST | `/extensions/google/email-conversation-imports/` | Atomically publish selected reviewed message IDs and optional explicit Lead link. |
| POST | `/extensions/google/email-threads/{uid}/selection/` | Owner's explicit sync choice, expected thread version and strict boolean enabled. |
| POST | `/extensions/google/email-threads/{uid}/sync/` | Refresh one enrolled thread, never broadens selection. Body `{}`. |
| POST | `/extensions/google/email-sync/` | Refresh up to five owner-enrolled threads, oldest checked first, with per-thread status. Body `{}`. |

Collection parameters: `page_index`, `page_size` (1–100), `search` (subject,
addresses and normalized body), `ordering` (`sent_at`, `subject`, optionally
prefixed by `-`), and JSON `filters` with Contact, Company, Deal, Interaction or
thread or explicit `lead_uid` UUID. Discovery accepts only semantic search/filters. Unknown fields fail.

Manual creation requires `contact_uid`, `sender: {email, name?}`, `subject`, and
`body_text` (up to 100,000 characters). Optional fields are `to` and `cc` address
arrays (up to 100 each), `sent_at` with timezone, HTTPS `original_url`,
`company_uid`, `deal_uid`, `interaction_uid`, and `lead_uid` with its
`expected_lead_version`. Selecting a Deal requires its
Company. An existing Interaction must be active, kind email, include this Contact
and match that context. Provider IDs and actor/provenance cannot be supplied.

Gmail search accepts `query`, aware `time_min`/`time_max` no more than 90 days
apart, and optional page token. Single-message preview accepts `message_id`
and CRM context; import accepts its `preview_token`, exactly the same CRM
context and required `audience: "shared_crm_readers"`. Gmail IDs and RFC Message-ID remain
distinct; Gmail links are account-sensitive convenience references.

Selection body: `{"expected_version": 1, "enabled": true}`. New enrollment fixes
a server timestamp boundary; disabling stops updates, re-enabling starts a new
boundary, and reconnect alone preserves the prior boundary. Refresh returns
thread UID, version, last check time and `has_more`; large backlogs need another
check. The server rechecks grant/account/selection at commit and never scans
unselected threads. Thread metadata is inspected before eligible new message
bodies are fetched; each run stops at 25 messages, about 20 seconds of retrieval
work, or a 2 MiB batch boundary and reports any remaining backlog. Payloads over 8 MiB, unsupported bodies
fail safely. Ordinary errors are redacted 422 validation, 403 permissions,
404 missing record and 409 stale/changed source/relationship states.

Follow-up accepts `text`, `due_at`, `owner_uid`, optional `existing_task_uid`
with `expected_task_version`, and optional `lead_uid` with `expected_lead_version`.
Task and Lead must concern the email's Contact. An existing Task must be open;
reusing preserves its business fields and only adds the source reference. A
previously linked open Task is reused by default. Creates require create and edit;
reuse needs edit. Task, optional Lead linkage and audit commit together.

The CRM MCP exposes matching email list/get/create/follow-up and scoped Gmail
search/preview/import/selection/refresh operations. It uses these same services
and effective requester checks. Email text is untrusted content, not instructions.


## Conversation selection and MCP parity

Conversation preview accepts `message_id` (a search result used to resolve the
source thread), `offset` (default 0, at most 1000), and CRM context: required
`contact_uid`, optional `company_uid`, `deal_uid`, `interaction_uid`, and optional
`lead_uid` paired with `expected_lead_version`. The Contact and Lead must be
active and match. A page has at most 25 messages with a bounded text budget; the
response's `next_offset` is null at the end. More than 1000 source messages fails
explicitly. Search dates bound discovery; conversation review can include earlier
history, which the caller must review and select explicitly.

Conversation import accepts the same context, `review_token`, unique
`message_ids` (1–25 IDs from that review), and required
`audience: "shared_crm_readers"`. It re-fetches only selected IDs, validates their
fingerprints and source thread, then commits one governed message/link/audit
command fenced by active Contact/Lead versions and source grant. Context changes,
expired reviews, foreign IDs and changed messages produce 409; missing or invented
audiences produce 422. It returns saved `items` (UID, provider message ID,
subject, sent date), `thread_uid`, `interaction_uid`, `lead_uid`, `audience` and
current `sync_enabled`. Bodies are read separately. Same-source repeat selection
does not duplicate messages. New source mappings start with sync disabled;
import does not alter an existing mapping's explicit sync choice.

`crm_gmail_conversation_preview` and `crm_gmail_conversation_import` expose these
exact models directly through authenticated MCP. Use `crm_email_messages_list`
with `filters.lead_uid` and `crm_email_messages_get` to verify stored results.
There is no actor/credential argument. A caller's mailbox grant never authorizes
another user's source operations. Detail includes `lead_uids`, publication
audience, creator and source owner, plus `possible_duplicate` for another source
with the same RFC Message-ID. This marker is advisory and never merges records.
