# ADR 0002: Shared CRM email conversations and owner-selected synchronization

- Status: Accepted; implemented locally; email feature not deployed
- Original decision: 2026-11-10
- Amended: 2026-11-12
- User approval: selective import on 2026-11-09; shared-conversation model and
  this amendment on 2026-11-12
- Scope: selected historical correspondence, shared CRM history, explicit Lead
  associations and optional future replies from the same selected conversation

## Context

A user needs to add conversations they have already had with a person to that
person's Lead. Other authorised CRM users must be able to read the captured
history without access to the importing user's Gmail account. A Gmail URL in a
Task is only an external reference: it is not a stored email, a conversation
association or an enabled synchronization policy.

This amendment supersedes ADR 0001's exclusions of retained email bodies and
ongoing sync only for explicitly selected correspondence. Its Google connection,
verified identity, private credential and reviewed-publication boundaries still
apply. Acceptance records the product decision, not completion or permission to
import a particular customer's messages.

## Decision

Email capture is an explicit publication of selected correspondence into shared
CRM history. Gmail authorisation remains private to its connected owner. Sharing
the stored history and authorising future source reads are separate decisions.

### User workflow and historical selection

1. From the Lead's **Emails / Conversations** section, choose **Add email
   conversation**. The Lead and its Contact are explicit reviewed context.
2. Search the current user's connected Gmail account with bounded criteria.
   Search and preview do not persist CRM emails or start synchronization.
3. Review a conversation and select the historical messages to include. A whole
   selected conversation is a reviewed message set, not permission to read or
   import other conversations with that person.
4. Before publication, show the exact selection, message count/date range, CRM
   context and audience: **Shared with users who have CRM read access**. Require
   an explicit import action. A one-message import remains available.
5. Offer a separate owner action to sync future replies in this exact source
   thread. Importing history leaves this choice off.

Historical selection must be bound on the server to the verified actor, connected
account, selected message identities, reviewed content and CRM context. Source
changes require renewed review. Pagination and bounded batches preserve that
approved set and report partial progress; they cannot silently include newly
arriving messages, other threads or the rest of the mailbox. Historical capture
and the future-reply boundary remain independently enforceable.

### Ownership, sharing and permissions

The first shared release uses the existing Main Sequence caller and CRM
capabilities. All published messages, including their bodies, are readable by
users with `crm.read` in this CRM under existing platform policy. Lead ownership,
import authorship and possession of a source URL do not restrict that audience.
There is no private-email or selected-team visibility option in this decision's
first release. The UI must name the actual audience before import.

| Operation | Authority and visibility |
| --- | --- |
| Connect, search or preview Gmail | The connected mailbox owner with the existing source/import capabilities; this grants no other CRM user mailbox access. |
| Publish selected messages | The verified owner with the required CRM read/create/import capabilities, after reviewing the selection and shared audience. |
| Read published history | Any authorised CRM reader, without that owner's Gmail credentials. Lists, detail, search, counts and assistant reads enforce the same policy. |
| Enable, stop or explicitly refresh source-thread sync | That mailbox owner with the required CRM capabilities and a valid grant. Reading a shared conversation does not grant this authority. |
| Add messages from another user's mailbox | That user authorises their own source connection and explicit selection; the existing conversation gives no access to someone else's mailbox. |
| Create or reuse a follow-up | Existing CRM Task capabilities and relationship/version checks; this never authorises a Gmail read or sends an email. |

Credentials, refresh grants and provider access stay server-side. Display safe
provenance such as who published a message and when, while withholding credentials
and private connection controls. The original Gmail link is a convenience for a
person with source access; the stored CRM copy is what shared readers use.

Any future private or team-restricted email audience needs a separate permission
decision using supported Main Sequence policy. It must cover every read surface,
including body search, counts and MCP, and must not introduce another application
login, user/role database or a client-only visibility filter.

### Record model and explicit CRM associations

These are logical responsibilities; the existing Interaction and Google
connection are reused rather than creating competing conversation or identity
systems. Concrete API/schema additions require implementation and migration.

| Record or relationship | Responsibility |
| --- | --- |
| Mailbox connection | Existing per-user Google authorisation and stable source-account reference; private source authority, separate from shared CRM content. |
| CRM conversation | An existing or new core email Interaction holding shared business history, reviewed Contact participants and optional Company/Deal context. A manually recorded message can start a conversation without Gmail provenance. |
| Conversation-to-Lead association | Explicitly links the reviewed conversation to the intended Lead and its Contact. The same shared conversation is displayed from linked records; a matching Contact alone or a follow-up Task is not an explicit Lead association. |
| Email message | Stores sender, To/Cc, original subject, sent/internal/import timestamps, body availability, plain-text content and provenance. Messages remain separate from Notes and Tasks. |
| Source-thread/message mapping and sync selection | Records the owning actor/account and exact provider identities, the shared conversation they contribute to, enabled state, future-reply boundary and last successful check. CRM conversation identity is distinct from a mailbox's thread identity. |
| Follow-up Task | An optional typed source-email reference and the existing Contact relationship. A Lead may use the Task as `next_task_uid`; this is independent of the conversation's Lead association. |

Validate the selected Lead's Contact against the conversation's reviewed people.
Apply the existing Company/Deal consistency rules. Show the conversation on the
Lead, Contact and relevant Interaction/Deal views through those saved links;
do not copy its body into each record or silently attach every same-person thread.
Contact merge must preserve and reconcile these relationships.

Publication must persist valid message/conversation/context associations with
their audit evidence atomically per committed batch. The batch's explicit
selection and reported status must make partial imports visible. If an action
also promises a follow-up and Lead next action, its promised writes must be
atomic or exposed as clearly separate operations. Import never changes Lead
lifecycle status merely because an email was saved.

### Multiple mailboxes and duplicate handling

Keep source identities scoped to their verified owner/account. Reconnect and
retry must not create another copy of a message already captured from that same
source. Separate owners can explicitly contribute their own selected messages
to reviewed CRM conversation context without sharing their connections.

The initial policy preserves independently imported copies from different
mailboxes with their source attribution and makes possible duplicates apparent.
Do not automatically merge or authorise access based on a subject, participant,
Gmail thread ID or RFC Message-ID. Any later cross-mailbox consolidation must
preserve each source mapping, import audit and owner's independent sync authority;
stopping one source must not stop or impersonate another owner's source.

### Synchronization boundary and execution

Enrollment is per owner/account and exact saved source thread, off by default.
The server fixes a future-reply boundary when it is explicitly enabled. Existing
unselected history requires a separate reviewed import. Never enroll by Contact,
sender, domain, query result, connection or reconnect. Refresh, pagination,
recovery and retries cannot broaden the approved selection.

Check current capabilities, account/grant, thread selection and versions before
eligible body retrieval and again at commit. Persist source message identities
to prevent duplicates. Show enabled/paused/error state, last successful check and
any remaining backlog. After an uncertain write, read saved state before deciding
whether to repeat an operation; this does not restore command replay receipts.

The current local implementation refreshes under the authenticated owner through
the visible email reader or explicit HTTP/MCP calls. Its one-minute reader timer
is not unattended background synchronization. Continuous background execution is
separate work: it requires proven platform-delegated owner authority, durable
progress/recovery, revocation checks and a repository-declared Job. A workload's
process identity is not a substitute for that authority. This ADR does not claim
that such a worker exists or grant permission to use another person's mailbox.

### Content and lifecycle

Use bounded plain text, including safe HTML-to-text extraction, with no executable
markup or remote media. Exclude binary attachments and Bcc from the first release.
Missing bodies are explicit; unsupported sizes fail rather than silently saving
an incomplete message. Keep bodies out of collection payloads, audits and logs.

Stopping sync or disconnecting a mailbox prevents further source reads and fences
pending imports; it retains already published CRM history. Reconnecting the same
account does not add scope or start a new import. Re-enabling a stopped thread
sets a new future-reply boundary. Unpublishing, purge, retention changes, portable
email export and Gmail sending require separate implemented controls and must
not be implied by disconnect or a source-link removal.

## Implementation status and delivery consequences

The 2026-11-12 local implementation now includes reviewed, context-bound
historical message selection, `EmailLeadLink`, Lead conversation filters and
section, explicit shared audience, source attribution and advisory duplicates.
`crm_gmail_conversation_preview` and `crm_gmail_conversation_import` use the same
operations as REST. Import and future-reply enrollment remain separate actions.
Local fixtures verify source/selection boundaries and shared-reader access;
deployment and live-provider evidence remain separate release requirements.
Private/team-only visibility and unattended workers remain separate extensions.

The 2026-11-12 deployed Lead-search correction did not deploy email history,
import a customer's message or enable synchronization. Eric's external Gmail
reference in a Task is not evidence that these email records exist in production.

Migration `0014` adds source conversations and messages; additive `0015` adds
explicit conversation-to-Lead associations.
Hosted migrations run only through the existing `migrate-crm` Job, followed by
API/frontend rollout and live verification. Never migrate at API startup or use
a local session to migrate a hosted database.

## Verification required before declaring the shared release complete

- From a Lead, select several historical messages, review the exact shared set
  and audience, import it, and read it back from the Lead and Contact after reload.
  Confirm that unselected messages and other same-person threads remain absent.
- A second authorised CRM user can read the stored body without the importer's
  Google connection, but cannot search that mailbox or manage its source sync.
  A caller without CRM read access cannot obtain bodies, matches, counts or MCP
  history through another read surface.
- Two owners retain independent account/thread selections. Same-source retries
  and reconnect do not duplicate messages; cross-mailbox copies retain provenance
  and follow the explicit non-merging policy above.
- Explicit future-reply enrollment captures only eligible replies. Pause,
  revocation, account change, stale versions and uncertain results preserve the
  selection boundary and stop unauthorised commits. Disconnect leaves the shared
  records readable without implying purge.
- Lead associations agree with Contact/Company/Deal context; follow-up Tasks remain
  separate and preserve existing Task/Lead/campaign rules. Migration, catalog,
  current SDK contracts, real-provider pre-push and owned hosted integration checks
  accompany the release; schema compilation or fixture screenshots alone do not
  establish completion.

See [email concepts](../../concepts/emails.md), the
[current local API](../../api/emails.md) and
[delivery evidence](../../delivery/verification.md).
