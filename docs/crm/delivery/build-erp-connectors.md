# Build ERP connectors

Use an independently released connector for an external provider. The
connector owns provider calls, credentials, consent, normalization, and
connection lifecycle. The ERP registry owns installation identity and the
release that may serve each Environment workflow. The owning module
authorizes and writes business records.

## Choose the release and workflow

- Add a provider adapter to an existing connector when it shares that
  service's operating boundary and release lifecycle. BankingConnectors,
  for example, can serve statement files and a bank API through the same
  Finance reconciliation workflow.
- Give an independently operated connector its own CodeRepository and
  FastAPI release. Use a connector-owned MetaTables namespace and migration
  Job when the service needs persistence. Declare only the exact public
  callback paths the provider needs in the connector workflow.
- Reuse an ERP workflow when its capability and intake contract already
  fit. Declare a new module workflow when the business permissions,
  review process, or write contract differs.

## Implement the connector and its ERP integration

1. Serve a manifest at `GET /api/connector/v1/manifest/` identifying the
   connector, supported capabilities, and contract version. Use the owning
   workflow to determine the required capabilities. Keep provider-specific
   identifiers and SDKs inside the connector where possible.
2. Apply the verified Environment, actor, and installed binding at
   admission. Check ownership and the current provider grant before source
   reads. For reviewed writes, issue purpose-bound claims and authorize
   redemption for the exact module workload. Support durable disconnect and
   close the destination grant fence before reporting local disconnect
   complete.
3. Have the module resolve matches and authorize the selected business
   action. Fence the current admission and grant at the write boundary,
   and commit the business data, source provenance, and audit together.
   Keep action permissions in the owning code. For example, Finance uses
   `finance.configure` to set up a bank source and `finance.post` to
   post a receipt from that source.
4. Reuse or register the workflow's local screen in the shared ERP
   frontend. Its registration owns the title, route, default placement,
   and supported placements. Use the approved release-scoped connector
   transport and the owning module's API for reviewed business commands.

## Register and enable the workflow

The current registry accepts v1. Publish the approved release UID and
the existing list of ERP workflow keys. An ERP administrator publishes the
registry revision and then activates the binding in **Settings → Connectors**.
Where the workflow needs personal consent, the eligible user grants it
through the connector.

The proposed v2 format adds an optional `workflow_settings` map alongside
that list. Each entry can set `admin_only` and a single `placement`.
The admin gate adds to the existing workflow and action permissions.
The primary placement can be `connector_menu`, `module_menu`, or
`settings` with `admin_only: true`. The workflow and manifest supply
compatibility information. The frontend supplies screen metadata.
See the full Google Workspace and Banking example in the
[backend connector ADR](https://github.com/MainSequenceCorp/MainSequenceERPAPI/blob/main/engineering/architecture/adr/0002-provider-connectors-and-intake-ports.md#version-2-workflow-settings).

## Verify locally before requesting deployment

Use a ready MetaTables SQLite runtime and confirm the expected local
DataSource. Run the connector and ERP against isolated fixtures. Test the
published release and workflow pairing, activation, the permitted actor and
a denied actor, direct calls, consent, preview and review, and approved
writes. Exercise retries, stale claims, and disconnect against an in-flight
write for claim-based intake. Verify the browser route and approved menu
placement in the shared ERP build. Request explicit approval before any
platform deployment or triggering push or tag.

For rollout details, see the
[local ERP and registry runbook](https://github.com/MainSequenceCorp/MainSequenceERPAPI/blob/main/engineering/architecture/user-preferences-operations.md#publish-connectors-at-runtime)
and the
[frontend subapplications ADR](https://github.com/MainSequenceCorp/Main-Sequence-ERP/blob/main/engineering/architecture/connector-subapplications-adr.md).
Repository agents can use the
[connector development skill](https://github.com/MainSequenceCorp/MainSequenceERPAPI/blob/main/.agents/skills/domains/crm/development/build-erp-connectors/SKILL.md).
