# ADR 0005 · One ERP API deployment

**Date** 18 November 2026

**Status** Implemented and verified locally. Hosted rollout awaits validation and approval.

## Context

ERP already has one Command Center site and one API repository. Its 14 business
modules and shared User Preferences surface have separate API entrypoints.
That design requires 15 possible frontend bindings and local targets. The 13
expansion API workflow candidates have never been activated. The Environment
activation model already controls which modules can serve business requests.

## Decision

Deploy the internal ERP HTTP surfaces as one FastAPI application alongside the
existing ERP static site. Preserve the `crm-api.yaml` workflow and its existing
`crm` API, `migrate-crm` Job and `crm-assistant` keys. The site uses one
delegated `VITE_ERP_FASTAPI_RELEASE_UID` binding to `crm`. Local development
uses one loopback API and the existing verified SDK sign-in.

The root API composes module-owned HTTP applications. Existing API paths,
response and error contracts, operation permissions, service ownership, and
the CRM `/mcp` path and lifecycle remain in force. Optional module readiness
is evaluated separately from ERP liveness. An inactive module or a failing
optional schema binding leaves unrelated modules usable. The API release
itself has a shared crash, capacity, promotion and rollback boundary.

The first release preserves the existing CRM Google Workspace OAuth callback, consent, and API contracts.
The existing CRM assistant, migration Job and independently executed workers
retain their workload boundaries. The separate local customer-facing Commerce
preview retains its own ingress and authorization model.

## Authorization and storage

[ADR 0001](0001-user-preferences-and-module-activation.md) continues to define
Environment activation, private visibility, dependencies and the audit trail.
Base is required. Provisioning represents explicit server approval and
compatible schemas on the expected governed DataSource. An optional operation
requires activation of its module and prerequisites plus the verified actor's
existing operation permissions. Personal visibility affects the menu.

The shared entrypoint preserves each destination's identity and authorization
checks. Keep exact trusted ingress declarations, CRM requester-bound MCP checks,
worker admission, and policy-version and DataSource fences on cross-module
writes. Preserve the narrow Base-to-CRM projection needed for existing adopted
claims even when CRM business access is disabled.

The shared workload is a wider process trust boundary. Hosted readiness
requires an explicit review of MetaTables grants for each owned namespace,
private preferences and activation/audit writes, along with installed
existing Google OAuth bindings and platform delegation. If the platform
cannot provide an acceptable scoped Settings authority within this
deployment, keep the privileged settings operations behind a separately
authorized workload. Caller checks and deployment access grants are both
required.

## Release and recovery

The first API release is admitted by the push to `main`. The migration
Job uses the same candidate image, verifies the selected DataSource and runs
the configured providers in prerequisite order before API promotion. Each
provider keeps its models, namespace, version table, and revision history.
ERP activation is a separate, audited administrator action. API startup
performs no schema migration or activation write. The existing site uses its
own `-erp-ui` release after checking compatibility with the ERP API.

This decision reduces deployment coordination and bindings. Existing
same-source atomic workflows keep their transaction boundaries.

Preserve the existing CRM API and MCP consumers during cutover. Verify the
Base adoption state for the intended source as a separate operation. Preserve
backward-compatible revisions for rollback. After adoption, rollback must
select a compatible adopting revision and preserve identity projection.

## Verification

Use the verified ready local MetaTables SQLite DataSource. Exercise one
loopback API and site, Base and Settings, every provisioned module prefix,
direct URL and API denial for inactive modules, continued availability of
unrelated modules, real caller verification, CRM REST and MCP, and an atomic
cross-module handoff. Record local migration and application evidence
separately from workflow validation and hosted authorization. Obtain explicit
approval before a triggering push, tag, hosted migration or reconciliation.

### Local evidence

- Applied all 15 providers to a new, verified SQLite runtime and reconciled
  them again at their current revisions. Base reference data and the initial
  policy were provisioned explicitly.
- All 14 business modules returned HTTP 200 from their readiness endpoint
  through one loopback API when active. With only the reviewed set active,
  direct requests to nine inactive modules returned `module_disabled`.
  CRM bootstrap, the authenticated MCP catalogue and a read-only Contacts
  tool call passed.
- Disabling Sales denied a direct Sales request and Finance's order-to-invoice
  handoff while Base and Finance remained ready. After reactivation the invoice
  and versioned Sales link persisted together. The test restored its policy.
- Live Chromium verified Settings, Business Directory, Catalog, Finance and
  CRM at desktop and phone widths through one Vite proxy. Inactive Reporting
  displayed the policy denial without an API call. The frontend unit tests,
  theme audit and application/guide build passed. A fixture exercised the
  shared delegated connection with the Command Center SDK.
- The broad backend run had 500 passes, 64 skips and two connection failures
  from CRM fixture URLs fixed to the default port. The corrected fixtures and
  focused API and module-policy suite passed together (17 tests).

Hosted grants, exact workflow validation, and the production-engine cutover
remain open. Local tests used a disposable DataSource and policy scope.

This ADR supersedes the per-module API release guidance in the companion
ERP expansion plan and the deployment topology in ADR 0001. Domain API,
schema, migration and authorization decisions continue to apply.
