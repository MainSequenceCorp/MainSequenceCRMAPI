# ERP MCP phases 2–4 implementation and local verification

**Verified workspace** 19 November 2026

The local candidate implements the module operations described in
[ADR 0006](../adr/0006-erp-mcp.md). The full registry contains 341 tool
definitions, including 104 existing CRM tools and 237 ERP tools. The ERP
count includes the 16 read-only pilot tools and 221 additions. Discovery
filters the catalogue per requester, module activation, readiness and
workflow availability. The SDK publishes 25 skills under
`.tau/skills/<module>/<skill>/`. The ERP [tool map](../../../.tau/skills/erp/erp-workflows/references/tool-map.json)
is the exact inventory. The [CRM tool map](../../../.tau/skills/crm/crm-core/references/tool-map.json)
continues to describe the CRM tools.

## Implementation

| Phase | Code and workflow | Skill folders relative to `.tau/skills/` |
| --- | --- | --- |
| 2 | `api/erp/mcp/tools/{base,catalog,sales,finance,projects,people,collaboration,marketing,settings}.py` registers Directory and Catalog edits, Sales orders, Finance drafts and allocations, project delivery, People, internal discussions, Marketing drafts and personal Settings. | `base/base-directory`, `catalog/catalog-items`, `sales/sales-orders`, `finance/finance-documents`, `projects/projects-delivery`, `people/people-workforce`, `collaboration/collaboration-discussions`, `marketing/marketing-mailings`, `settings/settings-preferences`. |
| 3 | `api/erp/mcp/tools/{inventory,purchasing,manufacturing,finance}.py` registers stock reads and movements, Purchasing receipts and bill handoff, production work and valuation lookup. | `inventory/inventory-stock`, `purchasing/purchasing-orders`, `manufacturing/manufacturing-production`, `finance/finance-documents`. |
| 4 | `api/erp/mcp/tools/{commerce,reporting,finance,settings,catalog,marketing}.py` registers merchant drafts and checkout trace, report runs and schedules, saved bank reconciliation review, module activation preview, Base reference configuration, and local Marketing capture. | `commerce/commerce-merchants`, `reporting/reporting-runs`, `reporting/reporting-schedules`, `finance/finance-bank-reconciliation`, `settings/settings-administration`, `catalog/catalog-items`, `marketing/marketing-mailings`. |

`api/erp/mcp/owner_routes.py` attaches fixed route methods and action values
at startup, builds strict inputs from owner models, and invokes the owner
function once under the verified actor and ERP admission scope. Owner
functions keep their storage, policy, audit, transaction and concurrency
checks. Reference lookups use the admitted tools of the module that owns
each record.

The existing Tau bridge names remain `crm__call_tool` and `crm__list_tools`.
`erp_tools_describe` supplies the exact admitted input schema for a tool, or a
bounded page for one module. The full catalogue exceeded 500 KiB with expanded
schemas. The bounded lookup keeps routine schema discovery small. Standard MCP
clients can still use `tools/list`.

Banking calls require the owner's operating company configuration. Marketing
queue, capture and event simulation use verified local SQLite. Reporting
schedule create, update and activation require a fresh heartbeat for the
current requester in the local runtime. The requester can pause a local
schedule during worker recovery. Connector setup and provider operations
remain in their independent projects. The ERP runtime skill pack contains
business skills, including the Finance-owned workflow for saved evidence.

## Reviewed commands in the ERP screens

The existing owner review, audit and transaction paths apply. Adding these
commands to MCP requires confirmation the owner can verify for the exact
request, actor, Environment and target version, as described in ADR 0006.

| Owner | Commands reserved from the MCP inventory |
| --- | --- |
| Business Directory | `base_{parties,affiliations,addresses}_{archive,restore}`. |
| Catalog | `catalog_{items,categories,units,unit_groups}_{archive,restore}`. |
| Finance | `finance_{invoices,payments}_{post,void}`, `finance_allocations_reverse`, and `finance_bank_reconciliation_commit`. |
| Inventory and Manufacturing | `inventory_movements_{reverse,post_valuation}` and `manufacturing_orders_post_valuation`. |
| Commerce | `commerce_{sites,offers}_{publish,unpublish}`. Grant issuance and revocation also stay with the merchant's dedicated workflow. |
| Settings | `settings_module_activation_commit`. |

## Verification

The all-module loopback tests used ready MetaTables local mode with SQLite
at `/tmp/erp-mcp-pilot.sZcbraoG/pilot.sqlite`, DataSource
`fd16c3b9-0977-5226-b5a8-aff3f47c542b` and local activation scope
`20e7cbc7-8523-4724-96cb-fcd34c1ab54b`. The test fixture verifies the runtime,
path, source and activation scope before writes. A separate local activation
scope with CRM disabled verifies the 16 pilot tools. The Banking test uses
its own disposable database and synthetic connector fixture.

| Boundary | Observed local evidence |
| --- | --- |
| Catalogue, skills, authorization | 30 compatibility tests passed. They cover exact registered names, strict input and result schemas, primary skills, every published resource digest, and compatibility with the CRM definitions. Signed human and delegated requester checks cover denied unbound workloads, revoked write access, inactive owners and rejected browser Origins. |
| Directory and Catalog | All 16 pilot results matched REST in the CRM-disabled scope. |
| Sales and Finance | Quotation and confirmation produced the linked draft invoice with the expected decimal total. A stale order version was rejected. |
| Purchasing, Inventory and Manufacturing | A purchase receipt created its linked stock movement, the completed receipt enabled a draft vendor bill, and production consumed and produced stock through its ordered steps. Valuation was posted through the Manufacturing owner endpoint in the disposable fixture and its two-leg entries balanced when read through MCP. |
| Other modules | The all-module fixture exercised project task creation, private employee detail, project-scoped discussion, local Marketing capture and simulated engagement, a draft Commerce site, Settings preflight and personal preferences, and the Reporting run and local schedule lifecycle. It verified that a timezone edit preserves the user's saved language. |
| Banking | The four Finance MCP calls returned masked account data, the synthetic saved movement, its review UID and the previously recorded operation outcome. |
| Tau | A real local read-only Tau turn called `erp_tools_describe` for the Sales schema and then `sales_orders_list`. Both calls succeeded in persisted session history. |
| Build | All ten frontend tests, the strict API help build, frontend guide validation, and the TypeScript, Vite and Docusaurus builds passed locally. |

Test entrypoints are `tests/erp/mcp/test_catalogue.py`, `test_admission.py`,
`test_workflows.py`, `test_expansion_live.py`,
`tests/erp/crm/agent/test_mcp_skills.py`, and
`tests/erp/finance/test_banking_pilot_live.py`. The loopback tests take
`ERP_MCP_TEST_ORIGIN` for the CRM-disabled scope,
`ERP_MCP_EXPANSION_ORIGIN` and `ERP_MCP_EXPANSION_SCOPE` for the all-module
scope, and `ERP_MCP_TEST_SQLITE` plus `ERP_USER_PREFERENCES_DATA_SOURCE_UID`
for the verified database. The Banking fixture takes
`ERP_BANKING_CONNECTOR_PROJECT`.

The candidate remains local. Phase 5 requires approval, exact API, Agent
and site revisions, the approved Environment and grants, compatibility proof
for the hosted skill URI cutover, and the rollback set before promotion.
The local workflow definitions retain the ERP API key `crm`, migration Job
`migrate-crm` and Harness Agent `crm-assistant`. The Agent's
`mcp_applications` points to `crm`, and the API workflow deploys the API
before the Agent. The site publishes through its separate ERP UI release tag.
Use the Production baseline and documented URI migration from the
[phase 0 and 1 verification](erp-mcp-phase-0-and-1.md) when preparing the
rollback and compatibility checks.
