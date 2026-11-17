# ERP Base module

Read `engineering/base/README.md`, its verification record and the Base API ADR
in the API repository before changing Base. Step 1 is local-only; CRM extraction
is step 2 and requires a separate ADR and authorization after Base's gates close.

Keep Base services, API, models, metadata, migrations, tests, guide, scripts and
build configuration under Base-owned paths. Only the Base provider owns Base
tables and revisions. Never modify applied revisions or import CRM business code.
Frontend types and view state never own persistence or migration definitions.

Use the installed MetaTables and Command Center SDK skills for the relevant work.
Reuse existing verified platform identity and public SDK contracts. Do not add
Agents, MCP tools or an application user/role database to this API module.

Before migration, test writes or first deployment, verify actual MetaTables local
mode, ready SQLite initialization and the expected local DataSource. Never fall
back to a hosted source. Use the local launcher and real SDK sign-in; do not mock
authentication to claim integration success. Keep fixtures local and scoped.

Run the relevant local checks and record limitations. Platform deployment, hosted
migrations and any triggering push, tag or workflow reconciliation require the
user's explicit approval after local evidence is available. Local commits are
permitted. Do not add active Base workflows or start the next module before those
gates are satisfied. Preserve unrelated work from parallel sessions.
