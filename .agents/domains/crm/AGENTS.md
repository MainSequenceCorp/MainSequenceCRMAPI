# AGENTS.md

You are a dual-mandate agent. Follow the repository-specific instructions in this file and the
relevant skills, while also keeping in mind that application surfaces, data, and implementation
operate within the Main Sequence platform and must follow Main Sequence platform instructions.

## Repository-Specific Instructions

### Main Sequence CRM implementation routing

Maintain the implemented CRM against the current `src/erp/crm/` models, services and repositories (including the optional `src/erp/crm/campaigns/` module and its `CampaignStore`), mounted `api/erp/crm/` routes, `tests/`, and MkDocs pages under `docs/crm/`. Read the relevant project skill and installed domain/SDK guidance before changing behavior. The paired frontend owns its Vite source and end-user guide. Preserve existing repository/platform instructions and scaffold markers.

Use `.agents/skills/domains/crm/development/` for CRM repository implementation and maintenance, with the appropriate installed `.agents/skills/mainsequence/`, `.agents/skills/metatables/`, `.agents/skills/command-center/` or optional `.agents/skills/ms_tau_sdk/` guidance. Project skills must remain outside SDK-managed/pruned namespaces.

`.tau/skills/crm/` holds the CRM assistant's skills, the only skills the deployed Agent reads (ms-tau-sdk ADR 0025). Six are business usage skills for CRM MCP operations: `crm-core`, `crm-deals`, `crm-prospecting`, `crm-prompters`, `crm-discovery`, and `crm-campaigns`. `crm-core` consolidates Contacts, Companies, affiliations, Notes, tags, activity, Tasks, Interactions, owners, settings and merge previews. Use these skills for operating the CRM through its advertised tools. They do not grant permissions or authorize repository changes. Exact enabled tool schemas and actual business results remain authoritative. The API publishes `.tau/skills/crm` itself with the Main Sequence SDK's `skills_extension` on authenticated `/mcp`, so the assistant's skills and the published skills are one set; development skills stay under `.agents/skills/` and are never published or read by the assistant.

Solution Selling usage skills are nested under `.tau/skills/crm/solution-selling/`: `crm-prospecting`, `crm-prompters` and `crm-discovery`, beside `solution-selling-workflow`, the assistant's own Solution Selling workflow skill that `.tau/SYSTEM.md` names; it is not part of the static repository's pack. Core, Deal and Campaign skills stay directly under `.tau/skills/crm/`. Shared MCP guidance and tool allocation live in `crm-core/references/mcp-usage.md` and `crm-core/references/tool-map.json`, served once and linked from other skills through `skill://` URIs. Keep the six usage skills identical to the static repository's usage pack. `tests/erp/crm/agent/test_crm_skill_pack.py` checks tool coverage with Solution Selling enabled and disabled; `tests/erp/crm/agent/test_mcp_skills.py` verifies publication and authenticated file access.

Target: Python FastAPI, Main Sequence MetaTables, Vite React/TypeScript and the Command Center SDK. Reuse the platform's caller identity, which the SDK's request identity verifies in the API; do not rebuild login/users/roles or adopt Supabase/Django/Frappe/Node business backends. Atomic supplied behavioral inspiration; current CRM contracts and installed SDKs govern maintenance. Tau is not required for deterministic tracking or data transfers.

Prove atomic governed commands and fresh-process catalog binding before completing mutation changes. Report executed checks separately from specified, mocked or unexecuted tests.

Before pushing, run the relevant API and documentation checks locally.
Install the repository hook with `git config --local core.hooksPath .githooks`.
It checks the clean committed revision, API contracts and strict documentation.
For changes to mutations, verify an explicitly owned disposable fixture through
create/update/read-back and clean up after confirming current state. Never replay
an uncertain write.

Current repository decision (2026-09-23): Alembic `0003` removes `command_receipt`; CRM commands no longer require `Idempotency-Key` or promise replay. Keep version fences and governed atomic writes, and read server state before retrying an uncertain write.

Current repository decision (2026-09-23): Alembic `0004` removes the CRM application workspace table and every `workspace_uid` column. The CRM has singleton settings and direct record foreign keys; platform-injected identity/policy remain authoritative. Do not reintroduce an application workspace, workspace-scoped keys, a workspace UID resolver, or a global workspace mutation epoch.

Current repository decision (2026-10-03): hosted CRM databases are migrated only by the `migrate-crm` Job (`jobs/erp/crm/migrate.py`) that `.mainsequence/workflows/crm-api.yaml` runs before it deploys the API and the CRM assistant. That file is the repository's only workflow file: declare every API, agent and scheduled Job in it, give each API or agent its own `prepare_image` step and a `deploy` step downstream of `migrate`, and keep scheduled Jobs out of `execution.steps`. Local development applies revisions with `metatables --local migrations upgrade --provider src.erp.crm.migrations:migration`. Never run `metatables migrations upgrade` or `downgrade` against a hosted runtime, and never migrate at API startup. Revisions branch raw PostgreSQL SQL on `op.get_bind().dialect.name` so the whole history also runs on local SQLite.

Current repository decision (2026-10-04): `api.erp.crm.main.create_app()` installs `mainsequence.server.fastapi.install_request_identity` once, after every REST route is mounted; Main Sequence's FastAPI launcher (PodDeploymentOrchestrator `3057764`) refuses to serve the API without it. Deployed, it verifies the platform-signed caller assertion of every request; locally, a direct Bearer token. CRM code takes the effective actor only from `authenticated_actor()`, which reads the verified caller with `User.get_logged_user()` and uses the signed `User.get_requester()` when present. Handlers must use this integration rather than `request.state.user_uid`: the launcher does not inject that state. Never add a UID-header, request-state or process-credential fallback. Mount every route the workflow declares as `public_ingress` on the application itself, not only through an included router: FastAPI 0.141 hides included routes from `app.routes`, where the launcher and the SDK look for them, and the API then fails to start. `api.erp.crm.local` presents its SDK sign-in as the Bearer token that the same integration verifies.

Current repository decision (2026-10-09, amended 2026-10-12; ADR 0005): CRM business tools live in `api/erp/crm/mcp_tools.py`, served through authenticated stateless `/mcp` installed after request identity. Hosted MCP business calls use the signed requester when present and check that person's CRM capabilities on every call; never fall back to the agent's permissions. A direct hosted caller is admitted only after a caller-scoped directory lookup proves it is an active human, then its own capabilities are checked. An unbound workload remains denied, including one with privileged Team memberships. REST uses the verified requester when present, otherwise the verified caller. `.tau/extensions/crm.py` only adds the local generic MCP bridge; hosted application tools come from Tau's workflow-declared `mcp_applications`. The API resource key is `crm` because the MCP application prefix cannot contain hyphens. This key change recreates its release when applied: coordinate the frontend release UID, OAuth callbacks, workload Team membership and grants before publishing. The assistant deployment waits for API deployment, which waits for migration. Never infer that chat readiness proves MCP authorization or persistence readiness.

For every material change to a CRM model, business rule, mounted API behavior, persistence, transfer workflow, or delivery status, use `.agents/skills/domains/crm/development/maintain-crm-documentation/SKILL.md` and update the relevant MkDocs concept and API/delivery pages in the same change. Run `mkdocs build --strict` and report its result; keep planned or unverified behavior labeled.

### CodeRepository-Specific Instructions

This file routes coding work in the repository. The separately deployed CRM
assistant uses `.tau/SYSTEM.md` for its conversation role and the API-owned
`/mcp` catalogue for its CRM tools. Tau also loads this file as project context, but these coding
instructions do not grant that runtime file editing, shell access, platform
MCP access, or CRM permissions. In CRM chat, follow the runtime directives and
describe only actions supported by the effective tool catalogue and verified
tool results. The Agent Card supplies the display name, not executable
capabilities.

The managed CRM assistant intentionally excludes Tau's base coding tools and
Main Sequence MCP. Treat that as its chosen runtime profile, not a capability
defect. Application MCP is independent of broad Main Sequence MCP; Tau 2.0.13
retains skill-scoped `read`. Customize conversation in `.tau/SYSTEM.md`.

Do not remove the `