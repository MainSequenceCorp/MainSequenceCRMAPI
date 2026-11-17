# Collaboration local verification — 17 November 2026

The local cycle is verified; hosted release remains unapproved.

## Runtime and migration

Actual MetaTables Local: local_mode true, dialect SQLite, active/ready bootstrap,
source `75b7fd29-3b1f-565d-be8d-a3a27d643de2`. Own provider applied reviewed revision
0001, four tables, own namespace/version table. Repeated upgrade preserves Base,
Projects and People revisions. Every local write rechecks the source. Fresh-process
API import excludes all other business modules; saved shared discussion read survives
restart. Disabling Projects preserves standalone shared operations; disabling the
module removes business routes. Wrong-source launch fails before writes.

Local API serves loopback 38711 with actual SDK identity. An initial test caught that
request identities expose authenticated username rather than User profile fields;
identity label extraction now uses the installed request contract. No forged test
identity was passed through HTTP. Distinct policy actors exercise authorship rules
inside the service tests only. All fixture UUIDs are cleaned by their owner.

## Backend evidence

Focused suite: 4 passed in 8.96s. Full ERP regression: **522 passed**, 41 existing
warnings, 152.97s. Additional post/close concurrency acceptance test: **1 passed**,
1.14s after the full run; business code unchanged. The existing CRM suite includes
local PostgreSQL compatibility fixtures; all new Collaboration mutation/migration
and integration scenarios use actual Local SQLite through MetaTables.

Covers authorship, retained revisions, retraction tombstones, reader/moderator rules,
closed/archive lifecycle, forbidden identity fields, strict positive versions,
atomic rollback, concurrent posts and post versus close, 27-message pagination,
default shared-only counts/search, per-project collection, revoked owner access to
content/history/audit/counts, read-only Projects flags, migration isolation, restart,
SDK collection/discovery JSON schemas, actual HTTP authentication, hostile origins,
forged caller headers and disabled optional integration.

Every model column has label/description metadata. Two human search phrases per
model return its table within the first five actual local catalog hits. Model-owned
schema and independent provider identities remain explicit. Ruff and strict MkDocs
build pass; no applied revision was rewritten after installation.

Reproduce with exact `COLLABORATION_LOCAL_SOURCE_UID` and `PROJECTS_LOCAL_SOURCE_UID`:

```bash
.venv/bin/python -m pytest tests/erp/collaboration -q
.venv/bin/python -m tests.erp.collaboration.run_browser --frontend <frontend-root>
.venv/bin/mkdocs build --strict -f documentation/collaboration/mkdocs.yml
```

Use the frontend's Node 24 and Playwright runtime for the browser runner. The full
ERP suite also needs the established local PostgreSQL binaries and other modules'
exact source variables documented in their verification records.

## Companion application and guides

Real local browser passed discussion creation with audience confirmation, plain-text
script content without execution, author edit/history/retraction, lifecycle,
concurrent edit/reload, unsaved navigation protection, actual committed message and
discussion response loss followed by original-UUID GET (exactly one POST each),
keyboard project selection, linked Projects navigation and no other module transport
calls before deliberate navigation. Six SDK viewports pass in light/dark. The tablet
check initially caught width overflow; plain detail content and a compact audience
summary fixed it without overriding SDK geometry. Screenshots visually reviewed.

Held/failed readiness and explicit Retry pass. Both feature Help links and return to
application pass. All **60 built guides** pass shared General/Modules ordering,
module links and desktop/mobile/light/dark navigation. Existing ERP submenu/history/
mobile checks pass. Nine frontend unit files, TypeScript, docs validation, theme
audit and combined Vite/Docusaurus build pass. Build size notices and two existing
touch-hover warnings remain non-failing; no new theme violations.

## Limits and next gate

The source mapping documents intentional omissions. Shared audience is broad and
not private. Project access follows the current owner's module-level policy; no
new per-project ACL is implied. No external notifications or CRM email migration.
Production-engine concurrency, hosted Team/grant policies, delegated transport,
resource/tag selection and hosted rollout remain unverified. The workflow candidate
is inactive. No platform migration, push, tag or deployment occurred. Marketing may
now begin its local review/ADR cycle under the user's existing authorization.
