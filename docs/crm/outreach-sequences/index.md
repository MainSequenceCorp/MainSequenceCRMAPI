# Outreach Sequences

The optional Outreach Sequences extension implements the task graph in
[ADR 0001](adrs/0001-campaign-task-graph.md). It provides
a live DAG of prompted task definitions, explicit Contact enrollment, one CRM
Task per participant step, stable per-Contact prompt assignments with A/B
comparisons and descriptive reporting. It is enabled by
`extensions.campaigns.active` in `config/erp/crm/settings.yaml` and mounts below
`/extensions/outreach-sequences/`.

- [Concept](../concepts/outreach-sequences.md): definitions versus instances,
  lifecycle, progression, live editing and comparisons.
- [HTTP and MCP API](../api/outreach-sequences.md): routes, payloads, error codes,
  recovery and the 21 MCP tools.
- [Persistence](../delivery/persistence.md#campaigns-revision-0013): the six
  tables added by revision `0013`.
- [Verification](../delivery/verification.md#campaigns-module-2026-10-24):
  executed checks and remaining hosted evidence.
- [Implementation plan](implementation-plan.md): the contract decisions taken
  during implementation.

The paired frontend exposes an Outreach Sequences section with a visual designer,
participant enrollment, task execution forms and comparison tables; its user
guide documents the Dubai walkthrough. The `crm-outreach-sequences` usage skill is
published with the API's MCP skill pack and mirrored in the frontend pack.

The public rename is a local change. The historical verification record covers
the original Campaigns release and its task graph behavior.
