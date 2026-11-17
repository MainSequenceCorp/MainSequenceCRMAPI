# Mailing and subscription concepts

Base owns shared identity. Subscriber binds an active Base person to a normalized
email already present on that person; both are immutable. Email is unique globally.
Subscribe/resubscribe/withdrawal requires explicit evidence and positive version
fences. Marketing has its own reader audience; captured identity/content is an owned
snapshot. This evidence is operational data, not a legal-compliance determination.

Mailing draft content includes internal name, subject, plain text, preview sender
and source label. Draft audience has at most 100 unique Subscribers. Queue requires
at least one subscribed member and explicit local-only acknowledgement. It freezes
content and audience. Capture rechecks subscription and current Base address; invalid
references become suppressed results, not silent disappearance.

A batch processes at most 10 pending recipients: parent fence + 3 statements per
recipient + audit fits the installed 32-statement transaction bound. Subscriber
version guards serialize unsubscribe versus capture. If any guard fails, the entire
batch rolls back, including payload/event/audit. Subsequent read/retry sees current
subscription. Parent guards serialize audience edits, queue, capture and cancellation.
Remaining pending recipients are resumable across process restarts.

Capture stores sender, address, subject, text and local_capture mode on Recipient.
Captured is never labelled sent or delivered. Completion means no pending recipients.
Cancellation preserves earlier captures and marks remaining pending rows cancelled.
Each local result has an immutable DeliveryEvent. Simulated opened/clicked/replied/
bounced events require a captured recipient and operator evidence; unique kind per
recipient prevents duplicates. Bounce and positive engagement are mutually exclusive.

Optional existing CRM follow-up linking requires a simulated reply, a readable active
Task and the same Base person's active CRM Contact consumer identity. Marketing stores
only the Task UUID. The owner's existing read contract controls access; this does not
create a Task, run a Campaign or promise an atomic lock on a remote Task's later edits.
No source modules are imported by the Marketing core except its declared Base contract.
