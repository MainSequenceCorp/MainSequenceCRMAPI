# ADR 0006 · ERP MCP server, tools, and agent integration

**Decision date** 18 November 2026

**Revised** 19 November 2026

**Status** Phases 0–4 are implemented in the local candidate. Phase 5 was
approved and is blocked at [release preflight](../verification/erp-mcp-phase-5-preflight.md)
by the expired platform session. See the [baseline and pilot verification](../verification/erp-mcp-phase-0-and-1.md)
and the [expanded catalogue and workflow verification](../verification/erp-mcp-phase-2-to-4.md).

## 1. What will ship

One authenticated MCP server at `POST /mcp` on the ERP API release `crm`.
The existing `crm-assistant` Harness Agent will use that server for CRM and the
other ERP modules. The assistant rail and `/assistant` page will be available
from the shared ERP shell. An authorized user who has CRM inactive can still
open the assistant and use Directory, Catalog, and any other admitted module.

The first increment adds exactly 16 tools to the existing CRM catalogue
(`erp_modules_list`, six Directory tools, and nine Catalog tools). It performs
no new business writes. Sections 4 and 5 name the tools and their owner
entrypoints. The first increment must pass with CRM disabled before new
mutation tools are registered. Later increments cover all 14 business
modules plus Settings through the same server. Section 5 lists tool families
and records where a reviewed action stays in the ERP screens.

The deployment stays on the existing ERP API, site, and Agent resources.
The keys `crm`, `migrate-crm`, and `crm-assistant`, the Agent UID, and the Tau
default session handle `main_sequence_crm_assistant` carry forward. Business
storage, permissions, migrations, audit, and workflow rules stay with the
existing owners. See the [shared ERP API decision](0005-single-erp-api-deployment.md),
[module registry](../../../src/erp/modules.py), and
[CRM MCP contract](../../../docs/crm/api/mcp.md).

## 2. Repository structure and responsibilities

The API repository owns this package. Each module file exports
`register_tools(registry)`. The shared registry imports these functions explicitly
and installs the catalogue once at startup.

```text
api/erp/mcp/
  __init__.py
  server.py                    # install_erp_mcp, SDK transport and request context
  registry.py                  # explicit tool definitions and catalogue composition
  admission.py                 # verified person and per-tool module/capability admission
  contracts.py                 # shared list/detail inputs and structured tool result
  owner_routes.py              # strict invocation of fixed owner methods and routes
  tools/
    __init__.py
    erp.py                     # module discovery and bounded tool descriptions
    base.py                    # Directory tools over Base owner services
    catalog.py
    crm.py                     # adapter for the existing CRM tool builder
    sales.py
    finance.py
    projects.py
    people.py
    collaboration.py
    marketing.py
    inventory.py
    purchasing.py
    manufacturing.py
    commerce.py
    reporting.py
    settings.py
tests/erp/mcp/
  test_catalogue.py              # tool names, metadata, schemas, and skill ownership
  test_admission.py              # identity, module policy, readiness, and permissions
  test_workflows.py              # owner REST parity for all 16 tools with CRM disabled
  test_expansion_live.py         # loopback commercial, stock, manufacturing, and other workflows
tests/erp/crm/agent/
  test_mcp_skills.py              # SDK discovery, file digests, and link integrity
```

| Existing path | Change |
| --- | --- |
| `api/erp/main.py` | Replace the shared app's call to `install_crm_mcp(application)` with `install_erp_mcp(application, module_apps=...)` after installing SDK request identity. Pass the already-created module applications indexed by module key, including `user_preferences`. Use the root application for CRM. The module applications supply their existing stores and runtime state. |
| `api/erp/crm/main.py` and `src/erp/module_access/http.py` | Add an exact path exemption option to CRM admission. In the shared factory, exempt `/mcp` for all methods so SDK transport handles methods and Origin even with CRM disabled. Keep existing CRM REST and connector ingress checks. The standalone CRM factory continues to use its CRM-only installer and existing module policy. |
| `api/erp/crm/mcp_server.py`, `api/erp/crm/service_adapter.py` and `api/erp/crm/mcp_tools.py` | Reuse requester verification and factor CRM request and runtime construction for both installers. The ERP local launcher binds CRM services only when a call needs CRM. Register `build_crm_tools(...)` in the ERP server with its existing argument models, result mapping, configured feature groups, diagnostics, and owner operations. Add per-tool admission metadata based on the capabilities each existing operation checks. |
| `api/erp/mcp/owner_routes.py` | Bind each opted-in MCP operation to a fixed owner method and route template at startup. Reuse its Pydantic body and path/query validation. Keep action and resource arguments private to the registration. Invoke that synchronous owner function once in the original verified actor and admission context. |
| `api/erp/<module>/main.py` | Supply mounted routes and existing service factories. The owner handles permission checks, validation, audit and atomic transactions. Finance exposes its included Banking routes to the adapter and shares `service_for` between REST and the typed allocation list. Base and Catalog pilot reads keep their existing service adapters. |
| `api/erp/user_preferences/main.py` | Extract `service_for(request, *, local)` from the existing scoped service factory. HTTP handlers retain their query validation. The ERP module tool and Settings tools use the extracted factory. |
| `src/erp/module_access/__init__.py` and `src/erp/user_preferences/admission.py` | Use the current `Admission`, `module_closure`, `require_active`, `require_integration`, and transaction guards. Share policy snapshot construction with the HTTP middleware so MCP and REST enforce the same provisioned-module set and policy version. |
| `.tau/SYSTEM.md`, `.tau/skills/`, and `.agents/agent_card.json` | Define the ERP operating role and publish the module-grouped skill tree in section 7. Keep the existing Agent Card `name` used by platform lookup during this rollout. Set the user-facing “ERP assistant” label in ERP bootstrap. |
| `src/agents/crm/local_mcp.py`, `.tau/extensions/crm.py`, `api/erp/local.py`, and `api/erp/crm/local.py` | Use the shared ERP API's `/mcp` through the existing bridge and `CRM_LOCAL_API_ORIGIN` loopback setting. Retain `crm__list_tools` and `crm__call_tool`. When the local launcher sets `crm_local_tau_origin` on the root app, project the same validated origin to the mounted User Preferences app for ERP bootstrap. |
| `.mainsequence/workflows/crm-api.yaml` | Continue to attach `mcp_applications: [{resource: crm}]` to `crm-assistant` and keep requester delegation, coding-tool exclusions, and API-before-Agent dependency. Deploy the existing resource identities through the approved workflow. |

Registry entries have `name`, `description`, `input_model`, `result_model`,
`owner_module`, `required_modules`, `owner_capabilities`, `kind`
(`read`, `preview`, `write`), `skill_path`, and a callable that invokes the
owner service. The authoritative domain permission checks still run inside the
service. New tools publish `inputSchema` and an `outputSchema` for the structured
result envelope with typed success data and allowed error codes. Phase 1 entries
declare `readOnlyHint: true`, a 60-second execution budget, and
`openWorldHint: false`. The registry refuses duplicate tool names and unknown
owners, dependencies, or primary skills. Use `user_preferences` as the service
owner for ERP module discovery, personal menu preferences, and Environment
activation. Treat that owner as the permanent Settings surface and use its
verified-person and administrator policy. It has no optional-module key to
pass to `Admission.require`. A Base-backed Settings tool declares `base` as
its service owner and uses Base admission. Register a
fixed tool for each operation, with fixed owner resource names, rather than
accepting an arbitrary model name, URL, or database query.

## 3. MCP request flow

### 3.1 Transport and identity

`install_erp_mcp` installs one SDK `MCPServer` using stateless Streamable HTTP
and JSON responses. Use `install_mcp` after `install_request_identity`, with the
SDK's authenticated route, Origin policy, and lifespan wiring. Before entering
the nested MCP ASGI transport, capture the owning FastAPI request context. Clear
it in `finally`. Initialization and skill discovery use the SDK transport
admission. Business discovery and invocation also require a verified person.

In hosted mode, use the platform-verified requester when present. Otherwise
use the existing caller-scoped active-human check from
`api/erp/crm/mcp_server.py`. A workload with no verified requester receives
`forbidden` even if its Team has ERP privileges. In local mode use the verified
SDK sign-in. Derive the Organization Environment and policy DataSource through
`scope_for_request` and the existing Settings scope configuration. Caller,
requester, Environment, capability, and DataSource are never tool arguments.

### 3.2 Discovery and invocation

1. On `tools/list`, resolve the person and read the Environment policy. For
   each registered entry, require its owner and declared dependencies to be
   provisioned, active, and ready, and require the person's operation-level
   capabilities. Use Settings readiness and the domain identity resolver.
   Reuse readiness and capability results within this request. A failed
   optional module check omits that module's tools while other admitted tools
   remain visible. A failed identity or shared policy check returns an MCP
   protocol error, because `tools/list` has no tool-result envelope.
   Personal menu preferences have no effect on business admission.
2. On `tools/call`, resolve the person and exact name, validate strict typed
   input, then reread policy and access for that tool's participating modules.
   Use the same module readiness and identity path as discovery. Construct a
   fresh `Admission` with the scoped active set and policy version, call
   `require` for the business owner and participants, and set the `admission`
   ContextVar for the operation. Reset the ContextVar in `finally`. The owner
   service performs record-level, role, configuration, and state checks. For
   conditional dependencies, keep the registry's hard prerequisites limited
   to requirements that apply on every invocation. Use the existing owner
   handoff to admit any participant required by the authorized record and
   action, such as Finance on a valued stock return.
3. Run synchronous owner services in an AnyIO worker thread that gets the
   request context. Once a write starts, preserve the CRM cancellation
   behavior with `abandon_on_cancel=False`. A lost or cancelled response
   requires authoritative read-back rather than automatic replay.
4. Apply typed output validation and the same field projection as REST.
   Return the same JSON envelope in MCP `structuredContent` and the text
   content. The new tools use `{"code":"ok","data":...}` on success. Errors use
   `{"code":"...","message":"..."}` with `isError: true`. CRM tools retain
   their existing codes and diagnostics. The SDK handles transport failures
   such as missing authentication or denied Origin before tool dispatch.

| New-tool result code | Condition |
| --- | --- |
| `invalid_arguments` | Missing or unexpected field, invalid type, out-of-bounds pagination, or malformed UUID. |
| `validation_error` | The owner rejects domain input. Preserve safe field paths and domain codes. |
| `not_found` | Unknown registered name or owner reports no such accessible record. |
| `forbidden` | Unbound workload, denied capability, denied row access, or denied workflow permission. |
| `module_disabled` | Owner or a required participant is inactive or unprovisioned. |
| `unavailable` | Policy, directory, owner service, or required schema/source is unavailable. |
| `conflict` | Stale record, current-state conflict, changed policy version, or owner duplicate conflict. |
| `result_too_large` / `internal_error` | Response exceeds the existing CRM response ceiling, or an unexpected failure occurs. Return a sanitized message and log the request correlation ID. |

For writes, reuse the exact owner input model for fields, decimal strings, and
required versions. Where the REST API separates the record UID from its body,
the tool input has the same UID plus those body fields. Preserve an owner
`request_uid` only for operations that support it. Skill text, model-generated
flags, and MCP annotations grant no execution authority. Keep the existing
128,000-character result ceiling and bounded search. Log only correlation ID, tool, owner,
duration, and sanitized result code. Treat business text and external evidence
as data.

### 3.3 Reviewed and cross-module writes

An ordinary change such as editing a draft uses the typed owner operation with
its existing version and authorization. Posting, reversal, sensitive access
grants, publication, archives where review is required, and Environment
activation commits are registered only when the owner exposes an enforceable
confirmation path. Use owner-issued, actor- and Environment-bound review
evidence covering the exact action, selection, versions and expiration when
available. Otherwise expose preview where supported and leave the commit in
the existing ERP screen. The implementation ledger marks those tool names as
deferred. No shared confirmation database is introduced by phase 1.

For handoffs, invoke the owning operation once. Its existing transaction
must carry all participating admissions, the exact DataSource requirement,
resource/version guards, and both sides' audit or downstream links. Follow the
[workflow dependency registry](../../../src/erp/modules.py). Examples include
Finance invoice creation from Sales, Purchasing receipts through Inventory,
Purchasing vendor bills through Finance, and Manufacturing completion with
Inventory and optional Finance. The Agent can explain and review these actions
but does not chain independent writes to simulate the atomic command.

## 4. Phase 1 tool contracts

All new tools below are read-only. `ListInput` accepts `page_index` (0–100000,
default 0), `page_size` (1–100, default 25), `search` (up to 200 characters,
default empty), and `archived` (default false). `GetInput` requires `uid` as a
UUID. Reject additional fields. Lists return the owner collection projection
`{items, pageInfo}`. The `pageInfo` fields are `pageIndex`, `pageSize`,
`totalItems`, `hasNextPage`, and `hasPreviousPage`. Gets return the owner's detail
projection including `uid` and `version` when present. Preserve typed values
such as decimal strings and existing record-level filtering.

| Tool names | Input and capability | Exact owner call and primary skill |
| --- | --- | --- |
| `erp_modules_list` | Empty object. Verified person with usable ERP policy. | User Preferences `Service.bootstrap` using its readiness and actor access projection. Return only `modules` (`key`, `title`, `provisioned`, `active`, `can_access`, `prerequisites`) and `policy_version`. Omit personal preferences and admin-only integration registry details. Skill `erp/erp-workflows`. |
| `base_parties_list`, `base_affiliations_list`, `base_addresses_list` | `ListInput` and `base.read`. Only `base_parties_list` accepts `kind` (`person` or `organization`). | Base `Service.collection` with fixed resources `parties`, `affiliations`, `addresses`. Skill `base/base-directory`. |
| `base_parties_get`, `base_affiliations_get`, `base_addresses_get` | `GetInput` and `base.read`. | Base `Service.get(resource, uid)` with the same fixed resources. Skill `base/base-directory`. |
| `catalog_items_list`, `catalog_categories_list`, `catalog_units_list`, `catalog_unit_groups_list` | `ListInput` and `catalog.read`. Only items accept `kind` (`product` or `service`). Only units accept `group_uid`. | Catalog `Service.collection` with fixed resources `items`, `categories`, `units`, `unit-groups`. Skill `catalog/catalog-items`. |
| `catalog_items_get`, `catalog_categories_get`, `catalog_units_get`, `catalog_unit_groups_get` | `GetInput` and `catalog.read`. | Catalog `Service.get(resource, uid)` with the same fixed resources. Skill `catalog/catalog-items`. |
| `catalog_units_convert` | Existing `ConvertInput` with decimal-text `quantity`, UUIDs `from_unit_uid` and `to_unit_uid`, and `rounding` (`up`, `half_up`, or `half_even`, default `up`). Requires `catalog.read`. | Catalog `Service.convert`. Returns `quantity`, `rounded`, both unit UIDs and versions, `rounding`, and `rounding_increment`. Preserve incompatible and archived unit errors. Skill `catalog/catalog-items`. |

[Directory handlers](../../../api/erp/base/main.py) ·
[Catalog handlers](../../../api/erp/catalog/main.py) ·
[Catalog conversion schema](../../../src/erp/catalog/schemas.py) ·
[ERP Settings bootstrap](../../../api/erp/user_preferences/main.py)

## 5. Planned catalogue after the pilot

Braces expand into individual tool names. For example
`sales_orders_{list,get}` means `sales_orders_list` and `sales_orders_get`.
Paths in the skill column are relative to `.tau/skills/` and each ends in
`/SKILL.md`. Every module's adapter lives in `api/erp/mcp/tools/<module>.py`
as listed in section 2. The selected owner handlers supply their route inputs
and service behavior. The
[verification ledger](../verification/erp-mcp-phase-2-to-4.md) records the
reviewed commits reserved under section 3.3. The [runtime tool map](../../../.tau/skills/erp/erp-workflows/references/tool-map.json)
lists the exact 237 registered ERP tools and their skills. In addition to
`tools/list`, `erp_tools_describe` returns admitted input schemas by module or
exact tool name in batches of at most ten.

| Phase and module | Primary skill | Exact tool names or families | Owner contract and constraints |
| --- | --- | --- | --- |
| 0–1 · CRM | `crm/crm-core`, `crm/crm-deals`, `crm/crm-outreach-sequences`, `crm/solution-selling/crm-prospecting`, `crm/solution-selling/crm-prompters`, `crm/solution-selling/crm-discovery`, `crm/solution-selling/solution-selling-workflow` | Integrate every existing tool from `build_crm_tools` and its [specific name-to-skill map](../../../.tau/skills/crm/crm-core/references/tool-map.json). Includes Contacts/Companies, affiliations, notes, tasks, tags, activity, email, deals/pipelines, prompters, assessment and sequence graph, participation and tasks. The workflow skill coordinates the Solution Selling tools. | [Existing builder](../../../api/erp/crm/mcp_tools.py) and [ADR 0004 cutover](0004-crm-outreach-sequences-and-marketing-replies.md). Existing CRM schema, feature flags, opt-ins, and result envelopes govern. |
| 2 · Business Directory | `base/base-directory` | `base_{parties,affiliations,addresses}_{create,update}` in phase 2. | [Base CRUD and lifecycle](../../../api/erp/base/main.py). `base.write` and shared identity adoption/lifecycle checks. |
| 2, 4 · Catalog | `catalog/catalog-items` | `catalog_items_{create,update}` in phase 2. `catalog_{categories,units,unit_groups}_{create,update}` in phase 4. | [Catalog CRUD and lifecycle](../../../api/erp/catalog/main.py). Item write and reference configuration permissions as enforced by the owner. |
| 2 · Sales | `sales/sales-orders` | `sales_orders_{list,get,create,update,quote,confirm,cancel,reopen}`. | [Sales order handlers](../../../api/erp/sales/main.py). `quote` invokes the owner's `quoted` action. Keep downstream record checks and Base/Catalog reference permissions. |
| 2, 3 · Finance | `finance/finance-documents` | `finance_{invoices,payments}_{list,get,create,update}`, `finance_invoices_create_from_sales`, `finance_allocations_{list,create}`. Add `finance_inventory_valuations_{list,get}` in phase 3. | [Finance handlers](../../../api/erp/finance/main.py). Allocation list requires document kind and UID. Sales invoicing calls the Finance owner transaction. Payments record observed funds. |
| 2 · Projects and services | `projects/projects-delivery` | `projects_projects_{list,get,create,update,create_from_sales,bill,start,deliver,close,reopen,cancel}`, `projects_tasks_{list,get,create,update,set_state}`, `projects_time_entries_{list,get,create,void}`. | [Project and task handlers](../../../api/erp/projects/main.py). Time entry creation uses the owning task UID. Project handoffs require Sales and, for billing, Finance. |
| 2 · People | `people/people-workforce` | `people_{employees,departments,absences}_{list,get,create,update}`, `people_{employees,departments}_{archive,restore}`, `people_employees_staff_task`, `people_absences_{submit,approve,reject,cancel}`. | [People handlers](../../../api/erp/people/main.py). Enforce private fields, Projects admission for staffing, and separate authorized approver for absence decisions. |
| 2 · Collaboration | `collaboration/collaboration-discussions` | `collaboration_discussions_{list,get,create,update,close,reopen,archive,restore}`, `collaboration_messages_{list,get,post,edit,retract,revisions}`. | [Discussion and message handlers](../../../api/erp/collaboration/main.py). Enforce discussion membership, authorship and Projects access for a linked discussion. |
| 2, 4 · Marketing | `marketing/marketing-mailings` | `marketing_subscribers_{list,get,create,set_subscription}`, `marketing_mailings_{list,get,create,update,queue,cancel}`, `marketing_recipients_{list,get,add,remove,events,link_followup}`. Add `marketing_mailings_capture` and `marketing_recipients_simulate` in phase 4 for the existing local runtime only. | [Marketing handlers](../../../api/erp/marketing/main.py). Recipient listing/adding is scoped by mailing. Preserve subscription checks and require CRM for linked follow-up. Live reply handoff remains under ADR 0004. |
| 3 · Inventory | `inventory/inventory-stock` | `inventory_{locations,stock_items,balances,movements}_{list,get}`, `inventory_locations_{create,update,archive,restore}`, `inventory_stock_items_{create,archive,restore}`, `inventory_movements_{create,create_from_sales,prepare,complete,cancel}`. | [Inventory handlers](../../../api/erp/inventory/main.py). Gate Sales deliveries and Finance valuations individually. No direct balance mutation. |
| 3 · Purchasing | `purchasing/purchasing-orders` | `purchasing_orders_{list,get,create,update,request_quote,confirm,cancel,reopen,close,fulfillment,create_vendor_bill}`, `purchasing_order_lines_{accept_service,revoke_acceptance,receive_stock}`. | [Purchasing handlers](../../../api/erp/purchasing/main.py). `request_quote` invokes `rfq`. Line commands require order and line UIDs. Physical receipt needs Inventory. Bills need Finance and Inventory if based on physical receipt. |
| 3 · Manufacturing | `manufacturing/manufacturing-production` | `manufacturing_boms_{list,get,create,update,activate,archive}`, `manufacturing_orders_{list,get,create,reserve,complete,cancel,valuation}`, `manufacturing_steps_{start,finish}`. | [Manufacturing handlers](../../../api/erp/manufacturing/main.py). Step commands require order and step UIDs. Production joins Inventory and only uses Finance when the valuation command and dependencies allow it. |
| 4 · Website and commerce | `commerce/commerce-merchants` | `commerce_{sites,offers}_{list,get,create,update}`, `commerce_checkouts_{list,get,payment_status,create_invoice}`, `commerce_grants_{list,get}`. | [Merchant handlers](../../../api/erp/commerce/main.py). Grant reads return status without tokens. Customer checkout and grant issuance remain in their existing dedicated flows. |
| 4 · Reporting and automation | `reporting/reporting-runs` | `reporting_definitions_{list,get,create,update,archive,restore}`, `reporting_runs_{list,get,start,advance,result,rows,verify,retry,recover,cancel,export}`. | [Report handlers](../../../api/erp/reporting/main.py). `start` invokes the owner queue operation. Keep source read authorization, row bounds, and private export visibility. |
| 4 · Reporting and automation | `reporting/reporting-schedules` | `reporting_schedules_{list,get,create,update,activate,pause}`. | [Schedule handlers](../../../api/erp/reporting/main.py). Enable scheduling only where the schedule worker is verified. Worker tick and operator endpoints remain on the worker surface. |
| 4 · Finance banking destination | `finance/finance-bank-reconciliation` | `finance_bank_accounts_list`, `finance_bank_movements_list`, `finance_bank_reconciliation_review`, `finance_bank_reconciliation_operation_get`. | [Finance banking handlers](../../../api/erp/finance/banking_routes.py). Review saved movements and read saved operation outcomes. Commit in the ERP screen. Use the approved connector binding where the owner requires it. |
| 2 · Settings personal | `settings/settings-preferences` | `settings_preferences_{get,update}`, `settings_locale_preferences_{get,update}`. | [ERP user preference endpoints](../../../api/erp/user_preferences/main.py) own menu choices. [Base preference resource](../../../api/erp/base/main.py) owns language and timezone. Both use the verified person's own record. |
| 4 · Settings administration | `settings/settings-administration` | `settings_module_activation_{get,preview}` and `settings_{operating_companies,currencies,languages,number_sequences}_{list,get,create,update}`. | [ERP activation endpoints](../../../api/erp/user_preferences/main.py) require Organization admin, complete proposed module set, and policy version. [Base configuration](../../../api/erp/base/main.py) owns reference data and its configuration capability. Activation commit stays in the existing reviewed UI until the owner can verify trusted MCP confirmation. |

## 6. Shared ERP bootstrap and assistant UI

1. In `api/erp/user_preferences/main.py`, extend
   `GET /api/erp/v1/bootstrap/` with `current_user: {uid, display_name}` from
   the verified person and `assistant` with the existing discriminated
   metadata shape. Move the metadata models out of `src/erp/crm/models/bootstrap.py`
   to `src/agents/assistant_contracts.py` and re-import them in CRM bootstrap.
   Reuse `resolve_assistant` in `src/agents/crm/discovery.py`. Both bootstrap
   endpoints use one resolver. CRM consumers continue to receive their
   existing `assistant` field. Resolve the existing Agent against verified
   branch, Environment, and runtime release evidence using its stable
   platform identity. Use the existing platform directory projection for the
   person's display name when available and `null` otherwise. The UI uses a
   generic signed-in label if the name is unavailable. Set `assistant.display_name`
   to “ERP assistant” in ERP bootstrap after lookup, independently of the
   deployed Agent lookup name.
2. A ready platform assistant returns `enabled: true`,
   `runtime: {mode: "platform"}` and the existing Agent/Environment UUIDs.
   A ready local Tau session returns `enabled: true`,
   `runtime: {mode: "local", base_path: "/tau"}` and null UUIDs.
   An unavailable runtime returns `enabled: false` with null runtime and
   UUIDs. Bound this optional lookup so unavailable Agent discovery does
   not prevent ERP bootstrap or normal module navigation.
3. In the frontend repository, extend `src/app/erp-settings-api.ts` with
   the new `ErpBootstrap` fields and update `routeModule` so `/assistant`
   and its subroutes are ERP-owned. Move `Assistant.tsx`,
   `assistant-config.ts` and their assistant-only dependencies from
   `src/erp/crm/assistant/` to `src/app/assistant/`. Replace the CRM bootstrap
   prop with the ERP viewer and assistant configuration. Keep the current
   Command Center Chat SDK components and default session handle.
4. In `src/app/App.tsx`, place the assistant around the shared shell after
   ERP bootstrap. Route module content through that shell before the
   assistant is mounted, so Directory, Catalog and other workspaces keep
   the rail. Remove the CRM-only Assistant navigation entry and its
   `/contacts` fallback. The shared launcher opens the rail and the existing
   expanded route. Direct navigation with no assistant runtime shows an ERP
   assistant unavailable state. Preserve identity mismatch checks and clear
   the assistant session on actor or Environment change. CRM readiness is
   checked only when opening CRM content.
5. Extend `tests/application/erp-settings.test.ts` and
   `tests/application/erp-settings.browser.mjs` for the new bootstrap,
   direct route, rail over non-CRM pages, disabled/hidden CRM, and unavailable
   assistant. Preserve existing CRM bootstrap and chat regressions.

## 7. Skill publication, compatibility and connector ownership

The API repository owns each runtime skill at
`.tau/skills/<module>/<skill>/SKILL.md`. Phase 1 adds
`erp/erp-workflows/SKILL.md`, `base/base-directory/SKILL.md`, and
`catalog/catalog-items/SKILL.md`. Add each later skill in its indicated phase.
The shared workflow skill's `references/tool-map.json` indexes every new
tool by exact primary skill. Keep CRM's existing mapping as the CRM source
and validate the two maps against the combined catalogue. The skill describes
the lookup, exact identifiers and versions, actionable result, and the
owner's review and recovery path. Leaf folder names are unique and match
the skill frontmatter. Development resources stay under `.agents/skills/`.

The shared server publishes `skills_extension(".tau/skills")`. This changes
`skill://crm-core/SKILL.md` to `skill://crm/crm-core/SKILL.md` and prefixes
Solution Selling and supporting references with `crm/`. Before switching the
root, snapshot current hosted `tools/list`, `skills/list`, and client consumers.
Update cross-skill links and the frontend's retained CRM reference copy.
Verify new URI reads, supported clients and the approved Campaign rename.
The shared server wraps the SDK publisher in
[`api/erp/mcp/compatibility.py`](../../../api/erp/mcp/compatibility.py).
Direct lookups can read the seven prior CRM skill URIs and their ten digested
files. The 21 former Campaign tool names dispatch directly to their admitted
Outreach Sequence handlers. Discovery advertises the current catalogue. The
standalone CRM launcher still registers only CRM tools. Skill discovery can
include guidance for a currently disabled module.

ERP's skill tree excludes provider-owned connector skills. [Connector ADR
0002](0002-provider-connectors-and-intake-ports.md) and [Google ADR
0003](0003-google-workspace-connector-extraction.md) keep OAuth, consent,
credentials, source connections, provider reads and normalization with
the independent connector projects. CRM's existing Gmail preview,
publication and selected-thread operations remain CRM actions with the
established connector binding, personal grant and destination fences.
Finance banking MCP covers saved destination evidence and reconciliation.
Provider setup, source-file intake and connector control use the existing
connector or configuration screens.

## 8. Integration examples

**Read with CRM disabled.** The person opens `/assistant` from Catalog.
ERP bootstrap returns the existing Agent UID. The Agent loads
`skill://catalog/catalog-items/SKILL.md` and calls `crm__list_tools`.
`catalog_items_list` is listed if Catalog and Base are ready and the person
has `catalog.read`. The Agent calls `crm__call_tool` with
`catalog_items_list` and `{"search":"consulting","kind":"service","page_size":10}`.
The registry installs Catalog admission and calls
`Catalog.Service.collection("items", ...)`. CRM tools are omitted, and a
direct CRM tool call receives the CRM adapter's denial result.

**Invoice from a confirmed order.** The assistant identifies the order with
Sales tools and opens the existing Finance handoff. When the commit contract
is available, `finance_invoices_create_from_sales` validates the source UID,
version and Finance inputs from the existing contract. The tool checks Sales
and Finance admission and invokes the Finance owner command once. That command
creates the draft and Sales link in a single transaction on the same source.
On timeout, read the order's downstream link and Finance's invoice state
before deciding whether any further action is needed.

## 9. Verification and rollout

| Gate | Evidence required |
| --- | --- |
| Baseline | Record actual endpoint catalogue and skill manifests for the intended Environment, active features and exact hosted/local revisions. Record approved CRM name and URI migrations. |
| Phase 1 | Only the 16 named new tools are registered. Prove REST/MCP result parity, strict input, skill-file hashes, existing CRM session history, delegated requester access, direct human access, unbound workload denial, unauthorized Origin, and CRM-off Directory/Catalog use. Exercise both the local Tau bridge and a direct SDK MCP client. |
| Phases 2–4 | Cover each registered tool with ownership, schema, permission, and owner-state tests. Exercise permission revocation between list and call, module disablement during a write, stale versions, wrong DataSource, uncertain responses, and connector closure. Run Sales-to-Finance, Purchase-to-Inventory-to-Finance, and production stock/valuation flows with rollback and audit assertions. |
| Production | Verify ready local MetaTables SQLite, the expected disposable DataSource, and real SDK sign-in before writing test fixtures. Record local results separately. Obtain explicit platform approval before a triggering push, tag, workflow reconciliation, hosted migration or deployment. Promote compatible API catalogue first, then the existing Agent and site. Verify actual hosted module activation, requester access, skill publication, and rollback against the approved revisions. |

One server keeps cross-module work in the same session and uses the already
shared API release. Separate MCP releases or agents per module would require
additional bindings and user session selection. The shared server makes
catalogue and resource contention a shared failure mode, addressed with
module readiness isolation, bounded results, and a recorded compatible
rollback set.

## 10. Implementation record

The verification ledger records the local candidate and the reviewed commands
that remain in the ERP screens. The phased plan in the frontend repository is
`engineering/architecture/erp-mcp-plan.md`.

| Phase | State at ADR revision | Evidence |
| --- | --- | --- |
| Baseline | Existing shared HTTP ERP API, CRM-only MCP, and CRM-scoped assistant bootstrap in the checked-out source. | `api/erp/main.py`, `api/erp/crm/mcp_server.py`, `api/erp/crm/main.py`, and frontend `src/app/App.tsx`. |
| 0 | Baseline captured | Read the deployed Production tool and skill manifests and recorded exact release, Environment and revision IDs. The [verification record](../verification/erp-mcp-phase-0-and-1.md) documents the 21 renamed tools and URI migration. |
| 1 | Implemented and locally verified | Shared `api/erp/mcp/` server, 16 read-only tools, three grouped skills, and ERP assistant bootstrap and shell. All 16 matched owner REST with CRM disabled. A second scope confirmed all 104 local CRM definitions remained unchanged. Local Tau and Chromium checks passed. |
| 2 | Implemented locally | Versioned Directory and Catalog edits, Sales and Finance drafts and handoffs, Projects, People, Collaboration, Marketing, and requester preferences. |
| 3 | Implemented locally | Inventory movements, Purchasing receipts and vendor bills, Manufacturing stock and work steps, and Finance valuation reads. |
| 4 | Implemented locally | Commerce drafts and checkout trace, Reporting runs and gated local schedules, Finance saved bank reconciliation review and operation lookup, and Settings policy preview and Base configuration. |
| 5 | Approved. Preflight blocked on sign-in. | The [preflight record](../verification/erp-mcp-phase-5-preflight.md) lists the remote commits, registered entrypoints and remaining compatibility and verification gates. |
