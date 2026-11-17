# ADR 0002: owner-authored confirmed service checkout plan

17 November 2026. Selected API extension for Website and commerce. No DDL: Sales
retains its existing provider/history; Commerce owns checkout/grant/offer persistence.

Add a complete public plan that validates Sales write/configure grants, strict order
input and current active Base/Catalog references, restricts this handoff to nonempty
service lines without CRM/discount overrides, and returns all confirmed Order, OrderLine
and audit statements. Register the Commerce source in the existing related-record map.
The caller joins its own checkout/offer/grant fences atomically on the same source.
Sales does not import Commerce models or execute a partial caller-provided plan.

Existing confirmed-order immutability and downstream cancellation guards apply.
Normal quotation/confirmation endpoints remain unchanged. Source navigation can use
the typed commerce:<UUID> link. Tests must cover permission denial, strict products,
rollback, deterministic duplicate handling and existing Sales/Finance behavior.
