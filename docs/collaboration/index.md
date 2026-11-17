# Collaboration API

Standalone internal discussions with optional Projects links. Collaboration owns
Discussion, Message, MessageRevision and AuditEvent, its provider and version table.
Platform identity remains authoritative; the verified username is captured when
posting or revising text. No client-authored identity fields are accepted.

- [Concepts and boundaries](concepts.md)
- [API contracts](api.md)
- [Local deployment and recovery](delivery.md)

CRM email, Gmail provenance, task graphs and mailbox authorization remain CRM-owned.
This release deliberately excludes external delivery, subscriptions, attachments,
unread state, rich HTML, private channels, direct messages and new Agent/MCP tools.
