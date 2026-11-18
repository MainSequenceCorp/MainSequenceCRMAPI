# ADR 0002 · Provider connectors and module intake ports

**Date** 18 November 2026  
**Status** Proposed. No code has moved. Implementation and verification are pending.

## Context

The ERP will connect to many external providers. Each provider has its own
credentials, consent programme, rate limits and release cadence, and one provider
can serve several modules: Microsoft Graph alone covers mail, calendar, directory
and files. Provider code inside a module's repository, migration history and
release cannot scale to that.

Today one provider is integrated, and it lives inside CRM:

- about 1,900 lines of Google code under
  [google_workspace](../../../src/erp/crm/google_workspace/),
  [emails/gmail.py](../../../src/erp/crm/emails/gmail.py),
  [google_routes.py](../../../api/erp/crm/google_routes.py) and
  [base_adoption/google.py](../../../src/erp/crm/base_adoption/google.py);
- two tables in CRM's namespace and revision `0008`
  ([google_oauth.py](../../../src/erp/crm/metatables/google_oauth.py));
- three `CRM_GOOGLE_*` Secrets and two public routes in
  [crm-api.yaml](../../../.mainsequence/workflows/crm-api.yaml);
- seven Gmail tools in [mcp_tools.py](../../../api/erp/crm/mcp_tools.py) and
  three Google destinations in the companion frontend.

Three platform facts shape the design. Each release runs as its own workload
User with its own grants and Secrets. A call from one release to another presents
the calling workload, not the person it serves (SDK 9.0.40). Workflow files name
other repositories' releases by repository name and resource key, never by UID.

## Inventory of existing integrations

| Integration | What it is | Decision |
| --- | --- | --- |
| Google Workspace: Contacts, Gmail correspondents, Calendar, selected email history and thread sync | The only third-party provider with credentials and API calls | Extract as the first connector. |
| CRM file adapters: `generic-csv-v1`, `atomic-csv-v1`, `atomic-legacy-json-v1`, `atomic-raw-json-v1`, `mainsequence-portable-v1` | Uploaded files; no credentials and no provider calls | Stay in CRM. Their commit path may later reuse the intake service. |
| Sales to CRM and Marketing to CRM reads | Loopback-only companion calls between modules | Not connectors. A hosted form needs its own ADR. |
| Owner ports between modules (`integrations.py`) | In-process module contracts | Not connectors. Unchanged. |
| Marketing mailings, Finance payments, Commerce checkout | Local capture and manual records; no delivery, bank or payment provider | Nothing to extract. A future provider arrives as a connector. |
| Assistant model provider and agent discovery | Platform-managed | Not connectors. Unchanged. |

Google is therefore the whole extraction. Everything else is either internal or
has no provider yet.

## Decision

Connectors never write ERP tables. ERP modules never hold provider credentials
and never call provider APIs.

| Piece | Where it lives | What it owns |
| --- | --- | --- |
| Intake port | This repository, one per module, CRM first | Resolving existing links and matches, and committing a record with its source link and audit event in one governed transaction. |
| Connector | One CodeRepository per provider | Provider calls, mapping, credentials, connection state, sync cursors and webhooks. |
| Connector kit | One small repository, consumed as a pinned package | The connection engine, claim tokens, standard routes, a fake provider, conformance tests and the repository template. |
| Connector registry | This repository, with the ERP-level settings of [ADR 0001](0001-user-preferences-and-module-activation.md) | Which connectors an Environment has installed and which ports each may use. Deferred until the second connector. |

Split connectors by authorization boundary, not by product: one OAuth client,
consent and API family is one connector. A connector declares capabilities, and
each capability binds to one module's port. Google Workspace is one connector
with `people.contacts`, `calendar.events` and `mail.messages`.

This ADR decides the flow where a person is present. Unattended sync, webhooks
and outbound actions need a separate ADR. CRM denies unbound workloads today, and
the Google module's
[email history decision](../../../docs/crm/google_workspace_module/adrs/0002-selected-email-history.md)
leaves unattended mailbox reads to separate work that needs platform-delegated
owner authority.

## Person-present flow

1. The browser, as the person, asks the connector for a bounded preview. The
   connector returns display fields and one claim token per candidate.
2. The browser sends the tokens to the module's `resolve` route. The module
   redeems them from the connector and returns existing links and matches.
3. The browser sends the reviewed values and one token to the module's `commit`
   route. The module redeems the token, validates the values against its normal
   create or update input, and writes the record, source link and audit event
   together.

The browser is the join between the two releases because the person's identity
does not cross a release-to-release call. The module's call to the connector is
only a claim redemption under the module's workload identity.

## Intake port contract

Each participating module mounts these routes under its existing prefix and
identity integration. Contract name: `erp.intake@v1`.

| Route | Contract |
| --- | --- |
| `GET /api/<module>/v1/intake/` | Accepted resources, their input schemas and the contract version. |
| `POST /api/<module>/v1/intake/resolve/` | Up to 50 claim tokens. Returns, per token, the linked record and version, or candidate matches. Writes nothing. |
| `POST /api/<module>/v1/intake/commit/` | One claim token, `action` (`create`, `link`, `update`, `skip`), optional `target_uid` and `expected_version`, and reviewed `values`. |

Payloads are the module's existing inputs, for example CRM's `ContactCreate`
and `InteractionCreate`. There is no parallel candidate schema. Capability
checks, version fences and the rule to read server state after an uncertain
write are unchanged. Intake routes are business endpoints and follow module
activation under ADR 0001.

CRM's port is the code that already exists: `source_links`,
`contact_matches_many` and `import_candidate` in
[store.py](../../../src/erp/crm/google_workspace/store.py), and `commit` in
[imports.py](../../../src/erp/crm/google_workspace/imports.py).

## Connector contract

Every connector serves the same authenticated routes. Contract name:
`erp.connector@v1`.

| Route | Contract |
| --- | --- |
| `GET /api/connector/v1/manifest/` | Connector key, adapter id, capabilities and their query schemas, contract version. |
| `GET /api/connector/v1/connections/` | The caller's own connection summary. Never token material. |
| `POST /api/connector/v1/oauth/start/`, `GET …/oauth/attempts/{uid}/`, `POST …/oauth/complete/` | The existing attempt, poll and complete exchange, unchanged in behaviour. |
| `POST /api/connector/v1/connections/{uid}/disconnect/` | Revoke at the provider, delete ciphertext, mark disconnected. |
| `POST /api/connector/v1/sources/{capability}/preview/` | Bounded candidates with claim tokens, for the caller's own connection. |
| `POST /api/connector/v1/claims/redeem/` | Workload callers on the consumer allowlist only. |

Public routes follow the platform's convention:
`/integrations/<provider>/oauth/callback/`, `/integrations/<provider>/oauth/done/`
and, later, `/integrations/<provider>/webhook/<topic>/`.

### Claim tokens

A claim token is sealed by the connector with AES-256-GCM, as the current
`Sealer` does. It binds the acting person, connection, provider account,
capability, candidate and a 15-minute expiry. It carries the connector key as a
routing prefix. External identifiers stay inside the token, as they do today.

Redemption returns the adapter id, account key, external id, payload hash and
normalized candidate. For content capabilities such as `mail.messages`, the
connector fetches the content at redemption, so bodies never pass through the
browser.

Two points need explicit review:

- The module sends the verified acting person's UID to `redeem`. The connector
  uses it only as authenticated data to open a token already bound to that
  person. A wrong UID fails to open the token. The connector never authorizes a
  provider read from that UID alone.
- The grant check moves. Today
  [emails/store.py](../../../src/erp/crm/emails/store.py) locks the Google
  grant row inside the commit transaction. After extraction the connector
  checks the grant at redemption, and the module must commit within 60 seconds.
  A grant revoked inside that window can still commit one reviewed batch.

### Provenance compatibility

The connector keeps adapter id `google-workspace-v1` and derives the account key
as the SHA-256 of `<actor_uid>:<google_sub>`, both as today. CRM creates the
`source_connection` row at first commit, using the existing unique key on
adapter id and account key. Existing `source_identity`, `email_thread` and
`email_message` rows keep matching without a data migration.

## Connector repository standard

| Concern | Standard |
| --- | --- |
| Repository | `ERP Connector <Provider>`; one workflow file. |
| Resources | One `fastapi` keyed `<provider>` in lowercase, one `migrate-<provider>` Job, optional scheduled Jobs outside `execution.steps`. |
| Persistence | Namespace `erp-connector-<provider>`, prefix `erp_connector_<provider>__`, its own provider and version table. Tables use the kit's column mixins. |
| Secrets | `ERP_CONNECTOR_<PROVIDER>_*`, declared in `access.secrets`. Never in YAML, Constants or tables. |
| Identity | `install_request_identity` once. No application users or roles. |
| Local mode | Runs against the kit's fake provider and verified local MetaTables. A real-provider check is a separate, labelled gate. |
| Delivery | Its own ADRs, tests, docs and release tag. Hosted deployment needs explicit approval after local evidence. |

The kit is consumed at a pinned tag, as `ms-tau-sdk` is. CRM does not depend on
the kit: the intake wire models live in CRM, and shared contract fixtures keep
both sides aligned.

### Bindings before the registry exists

- CRM reaches the connector with `ResourceRelease.by_uid(...).request(...)`.
  The release UID comes from one Constant per Environment,
  `ERP_CONNECTOR_GOOGLE_RELEASE_UID`, declared in `access.constants`.
- CRM's workflow declares the connector repository under `access.branches`.
- The connector's consumer allowlist is a Constant holding CRM's workload User
  UID.
- The frontend names the connector through `build_environment` with
  `resource_release: {repository, key}`.
- Local mode uses an exact loopback origin, as the Sales to CRM companion does.

The registry replaces these Constants when a second connector exists.

## Assistant and MCP

This ADR adds no Agent or MCP surface. Four of CRM's Gmail tools search or
preview a mailbox (`crm_gmail_email_search`, `crm_gmail_email_preview`,
`crm_gmail_conversation_preview`, `crm_email_thread_sync`). They cannot stay in
CRM after cutover, because CRM cannot read a mailbox as the person. Moving them
to the connector's own FastAPI MCP and adding it to the assistant's
`mcp_applications` needs a separate ADR. Cutover is blocked on it. The import
tools stay in CRM and take a claim token.

## Extracting Google

| Today | Destination |
| --- | --- |
| `google_workspace/security.py`, `service.py`: sealing, state, PKCE, attempt lifecycle, refresh, revoke | Kit. Google endpoints, scopes and ID-token verification go to the connector. |
| `google_workspace/store.py`: attempt and connection persistence | Kit store over connector-owned tables. |
| `google_workspace/store.py`: source links, contact matches, `import_candidate` | CRM intake port. |
| `google_workspace/imports.py`: People, Gmail and Calendar fetch and mapping | Connector. |
| `google_workspace/imports.py`: `commit`, `ImportDecision` | CRM intake port. |
| `emails/gmail.py` | Connector, capability `mail.messages`. |
| `emails/service.py`, `emails/store.py`, the three email tables | Stay in CRM. The grant lock is replaced by redemption. |
| `base_adoption/google.py` | Stays in CRM behind the intake port, renamed without the provider. |
| `metatables/google_oauth.py`, revision `0008` | Connector namespace. CRM drops its copies in a new revision after verified cutover. |
| `google_routes.py`, public ingress, `configure_google_oauth_secrets.py`, `google_workspace_module` docs | Connector repository. |
| `extensions.google_workspace` in `settings.yaml` | Becomes "a Google binding is configured". |

Steps, each verified locally before the next:

1. **Seam in this repository.** Add CRM's intake service and routes. Route the
   existing Google code through them in process, behind a connector interface
   whose redemption is a local function. No deployment change. Existing Google
   and email tests stay green.
2. **Kit and connector together.** Create both repositories. The connector is
   the kit's first consumer and passes the kit's conformance tests against the
   fake provider on local MetaTables.
3. **Remote port, local.** Switch CRM's connector interface to the release-call
   client and prove preview, resolve, commit and email import across two local
   processes.
4. **Hosted cutover, on explicit approval.** Deploy the connector and its
   migration Job. Create its Secrets. Register the new redirect URI in Google
   Cloud, because the public URL changes. Set the Constants, bind the frontend,
   then switch CRM.
5. **Connections.** Count connected rows at cutover. With none or few, people
   reconnect and no token ciphertext moves. Otherwise run a one-off governed
   copy with the same OAuth client and encryption key.
6. **Removal.** Delete the Google code, routes, public ingress, flag and Secrets
   from CRM. Drop `google_oauth_attempt` and `google_oauth_connection` in a new
   CRM revision. Applied revisions are never edited.
7. **Second connector.** Build one more connector before declaring either
   contract stable.

## Consequences

- CRM's release, Secrets and migration history stop growing with each provider.
- A commit makes one extra call. The connector is normally warm because the
  browser has just called it; CRM prewarms it at startup.
- Two releases must be compatible. The contract version in the manifest and in
  intake discovery gates each call.
- Google's restricted Gmail scope and its verification follow the OAuth client
  into the connector, unchanged.

## Rejected alternatives

| Alternative | Reason |
| --- | --- |
| Keep providers as flagged CRM extensions | Provider count multiplies CRM's code, Secrets, ingress and revisions. |
| One repository for all connectors | One workload would hold every provider's credentials, with one release cadence and blast radius. |
| Connectors write ERP tables through shared grants | Breaks module ownership; the owner can no longer guarantee atomic provenance and audit. |
| The module forwards the person to the connector | Not available: a release call presents the calling workload. |
| The browser carries full candidates and the module trusts them | Provenance becomes forgeable and message bodies pass through the browser. |
| Signed candidate envelopes instead of redemption | Viable, but adds key rotation, and content must be fetched server-side anyway. |

## Delivery and acceptance

- Verify the expected local MetaTables DataSource and initialized SQLite before
  any migration or write test, in both repositories.
- Step 1 passes when the existing Google and email suites pass unchanged and a
  new intake suite covers stale versions, expired and foreign tokens, duplicate
  links, partial failure and governed rollback.
- Step 3 passes when a second process redeems claims and CRM refuses an actor
  mismatch, an unlisted caller, an expired claim and a commit after 60 seconds.
- Before step 4, validate both workflow files with the branch validator,
  including the cross-repository `access.branches` grant and the frontend's
  `build_environment` reference. Neither has been validated yet.
- After step 4, verify the callback without a bearer token, a denied unlisted
  path, a reconnect, one reviewed import per capability and a fresh API read.
- Update the CRM MkDocs pages in the same change as each step and run
  `mkdocs build --strict`. Run the CRM agent pre-push gate before any push.

## Open questions

- Whether the kit is its own repository, as recommended, or a package here.
- How many live Google connections exist, which decides step 5.
- The ADR for connector MCP tools, which blocks step 4.
- The ADR for unattended sync, webhooks and outbound actions.
