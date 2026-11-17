# Marketing API

Independent Subscriber, Mailing, Recipient, DeliveryEvent and AuditEvent records
with Base person references and an optional read-only CRM Task link. Existing CRM
Campaign DAGs and email provenance remain unchanged. No new Agent or MCP.

- [Concepts and rules](concepts.md)
- [HTTP API](api.md)
- [Local delivery and recovery](delivery.md)

This local release captures messages without external delivery. Engagement is
explicitly simulated. It does not implement provider sending, scheduling, public
unsubscribe ingress, tracking pixels, A/B tests or reusable audience segmentation.
