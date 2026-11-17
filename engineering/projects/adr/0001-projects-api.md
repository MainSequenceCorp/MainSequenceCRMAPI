# ADR 0001: Independently owned Projects and services API

Status: accepted for local implementation, 17 November 2026. Based on the completed
[OpenERP review](../openerp-coverage.md). No Agents/MCP or platform deployment included.

## Ownership and scope

`src.erp.projects` owns Project, DeliveryTask, TimeEntry and AuditEvent, four tables
under namespace `erp-projects`, one explicit provider, own revision/version table.
Base is the only required business prerequisite. Source-order and billing adapters
are optional, lazy, separately enabled and authorized. Existing CRM task contracts
and data remain unchanged. Project staff are Base people; platform identity remains
injected. No employee record or new user/authentication model is created.

Projects are planned → active → delivered → closed, or cancelled. Start requires
active Base customer/company. Delivery requires at least one noncancelled task and
all such tasks done; task creation and delivery race through the parent version.
Delivered can reopen while unbilled. Billing closes the project. Closed/cancelled
are retained and immutable. A completed project can also close without billing.
Tasks have todo/in_progress/blocked/done/cancelled, description, due date, optional
Base-person assignee and whole-minute estimate. Edits and state changes require a
planned/active parent; completed/cancelled tasks reopen explicitly. Parent project
cannot change after task creation. No hard deletes are exposed.

Time entries are append-only task effort: work date no later than today, 1–1440
whole minutes and description; identity records the actor. Log only while project
is active and task not cancelled. Void requires expected versions, retains history
and removes effort from totals. Delivered/closed projects freeze effort until an
allowed reopen. Effort totals do not determine the fixed-price invoice amount.

## API and validation

`/api/projects/v1`: readiness; SDK discovery and paginated collections/detail for
projects/tasks; strict create/update inputs with client request UUID on create;
state commands with expected version; paginated task time history and append/void
commands. Readiness gates independent storage/Base bindings. References expose
public Base people/customers/companies and optional confirmed orders. List search,
state and project filters are allowlisted. Unknown inputs are rejected.

Capabilities: projects.read, projects.write, projects.manage, projects.configure.
Reading is required for returned records. Write covers drafts/task work/time;
manage covers project lifecycle and integration; configure covers audit. Verified
SDK Teams/identity govern hosted requests; verified local wrapper uses existing
signed-in identity. Access to a Project grants no foreign-owner permissions.

Every aggregate mutation carries expected_version. Child commands lock/fence and
increment parent version, preventing concurrent delivery, new tasks or time edits
from losing each other. State/history writes and audit commit atomically. Uncertain
creates reconcile by original UUID before replay; conflicts require reload.
Metadata and validation are module-owned. No application startup migrations.

## Selected integrations

A confirmed Sales order containing only current Catalog service items can create
one project and one delivery task per order line. Snapshot customer/company,
commercial source and line identities; retain Sales-owned downstream association
using its public owner-authored command plan. Same DataSource required for atomic
composition. Catalog is required only for this optional adapter, not Projects core.
Mixed physical/service orders and repeated projects per order are deferred.

After delivery, an authorized billing command creates one full draft invoice using
Finance's public `plan_from_sales`, then updates the Projects invoice link/state in
that same governed transaction. Finance owns all invoice validation, tables and
audit; Sales owns its link plan. The new public Finance plan preserves existing
`from_sales` API behavior. Duplicate or failed invoice creation rolls back all
owners. If the order was already invoiced independently, the command reports a
conflict and leaves the project unchanged. It never silently creates a second bill.
Subsequent posting/payment occurs in Finance. Standalone Projects works with both
adapters disabled; standalone billing is deferred. Optional reads use owner services
and same caller permissions; no foreign table/model imports by Projects.

## Companion frontend, tests and delivery

One shared ERP navigation group **Projects and services**, with Projects and
Delivery tasks. Companion UI consumes the above API, owns draft/permission/error
flows, history paging and Help. Three guides join the same General/Modules site.
Test real local SQLite, own migrations/restart/isolation, permission and version
races, delivery gates, effort bounds/reversal, source duplicate prevention, atomic
Sales→delivery→Finance trace and independent mode. Run real browser actions,
recovery, responsiveness, documentation navigation and build checks before closing.

Local API port 38691, exact source `75b7fd29-3b1f-565d-be8d-a3a27d643de2` after actual
runtime verification. First setup applies only this provider. An inactive workflow
candidate uses `-projects` tags and its own migration prerequisite. Platform release,
namespace grants, production-engine verification, hosted transport and activation
remain separate approved work. The local sequence may continue after local gates.

Implementation refinement: Base's public collection gains optional party-kind
filtering so Projects can select people with correct pagination. Projects does not
filter incomplete pages or read Base tables. Finance's source-invoice input also
validates due-date ordering before attempting a handoff; Projects validates its
billing input at the HTTP boundary for clear 422 errors.
