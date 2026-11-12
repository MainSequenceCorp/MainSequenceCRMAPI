# Selected email history

**Status: implemented in the local working tree; rollout and live verification
pending.** [ADR 0002](../google_workspace_module/adrs/0002-selected-email-history.md)
defines the sharing and selective synchronization policy.

Email history is core CRM data, independent of optional Solution Selling and
Google Workspace. One reviewed email conversation links a Contact to an email
Interaction; messages retain sender, To/Cc, original subject, sent/internal/import
timestamps, normalized plain text and manual or Gmail provenance. Company/Deal
context stays on the Interaction. Existing manual email Interactions can be reused
when the Contact and context agree. Contact merge moves conversation references.

The current sharing audience is every user with `crm.read` under existing CRM
platform policy, including access to the saved body. The private Google grant
only lets its verified owner search or retrieve source mail; sharing an email
record does not share that grant. The importing user must see this audience
before publication. Private and selected-team email visibility are not available.

Gmail access is actor-owned. Connecting, search and preview never store messages.
An explicit import saves only the reviewed message IDs and CRM context into shared
history. New source conversations start with sync off; adding history to an already
enrolled source does not change its sync choice. Account/message uniqueness prevents duplication across reconnect and retry.
A separate owner action enrolls one thread for future replies. The server checks
that selection, account, grant, capabilities and versions for every refresh and
again at commit. Same-contact threads are not implicitly eligible.

Synchronization uses exact Gmail thread reads and persisted message identities,
not mailbox-wide history. The reader checks its selected thread every minute while
open and visible; explicit HTTP/MCP refresh works without the browser timer.
There is no unattended scheduled workload or whole-mailbox backfill. Up to 25
unseen eligible messages are committed per run, with `has_more` for a backlog.
An uncertain result requires read-back; source uniqueness tolerates later repeats.

A follow-up is a separate Task with a typed source-email reference. It can reuse
an existing open Task without overwriting wording/owner/due date, and atomically
become the Contact's Lead next action. Task completion/archive clears that pointer.
Mail import itself does not change Lead status. At most one open, unarchived Task
can refer to a given email. Existing source links in Notes remain external links.

Bodies are bounded plain text, including text extracted from HTML without active
content. Binary attachments and Bcc are excluded. Missing supported text is explicit;
oversized/undecodable content fails rather than silently truncating. Full bodies
appear only on authorized detail reads, not collections, logs or audit diffs.

Disconnect stops provider reads and fences pending commits through grant checks;
published emails remain CRM records. This release has no email purge UI and does
not include messages in the existing portable export format. Operator retention
or export changes need explicit follow-up scope; disconnect is not a deletion claim.
See [API](../api/emails.md) and [decision](../google_workspace_module/adrs/0002-selected-email-history.md).

## Shared conversation and Lead association

Start from a Lead's **Email conversations → Add email conversation** action.
The Lead/Contact and optional Company/Deal/Interaction are chosen before review.
Conversation review returns at most 25 messages and a bounded text budget per
page, with no default selection. Select the exact historical messages, inspect
their dates and contents, and confirm **Share selected messages with CRM readers**.
A sealed 15-minute review binds actor, Google account, CRM context and exact
message fingerprints. Each page requires its own review/import. Later arrivals,
unselected IDs, changed contents and changed context cannot use that review.

`EmailLeadLink` explicitly associates the shared email Interaction with a Lead
for the same Contact. It is written atomically with the selected message batch
and audit event. Matching a Contact or linking a follow-up Task does not create
that association. Lead, Contact, Interaction and Deal sections read the same
stored messages; bodies are not copied into each context. Importer and source
mailbox owner are visible on the saved message, alongside shared audience and
source sync state. A reader without the source connection can read saved copies.

Each mailbox has independent source mappings and sync authority. Copies from
another mailbox remain separate with their own provenance; a matching RFC
Message-ID indicates a possible duplicate, never an automatic merge. The
conversation tab groups stored messages by shared Interaction, including sources
that explicitly selected the same Interaction. Private/team-only visibility,
Gmail sending and unattended background workers remain separate extensions.
