# Discussion concepts

A shared discussion is visible to every Collaboration reader. A project discussion
requires current Projects read access as well. Each write additionally requires
Projects write. A creator or moderator cannot override owner access. Collections
are shared-only by default, or restricted to one explicitly authorized project.
Authorization occurs before the count, search and pagination queries. Scope and
project association are immutable; create acknowledges the matching audience.

Open discussions accept content. Managers close, reopen, archive closed discussions
or restore archived discussions to closed. Author or manager edits open discussion
details; only the message author edits text. Author or manager retracts active text
with a reason. Retraction clears the current body and preserves prior revisions,
which require author/manager authority and the current discussion audience.

Each content mutation fences and increments the parent discussion version. Message
changes also fence their own version. A monotonic per-discussion sequence orders
messages; initial content, edits and retractions create immutable revisions. Parent,
message, revision and metadata-only audit commit in one MetaTables transaction.
No hard-delete route or foreign-table mutation is supplied.

Collections and messages use exact filters/counts and page-size limits of 100.
Messages are newest sequence first; revisions newest version first. Permission
flags inform screens but server checks remain authoritative on each operation.

Projects is optional and loaded through its public service adapter. No business
module is imported by the standalone Collaboration core/API. Project permissions
currently follow Projects' own module-level policy; no extra row-level ACL is claimed.
