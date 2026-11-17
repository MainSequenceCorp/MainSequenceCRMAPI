# CRM extraction and Base adoption — local verification

Date: 17 November 2026. Status: locally implemented and verified; platform release
and hosted frontend integration remain unapproved. This report describes the
working-tree implementation in both repositories, including the separate chat's
completed domain relocation. No push or deployment tag was created.

## Scope and ownership

[ADR 0001](../adr/0001-base-identity-adoption.md) preceded implementation. Base owns
shared identity, contact methods and employment; CRM retains its sales profile,
business history and an atomic compatibility projection. Existing CRM payloads
and UUIDs remain stable. Base's `0002` and CRM's `0016` are independent additive
revisions. Historical revisions were not rewritten. No Agent or MCP extension
was added, and Catalog or subsequent expansion modules were not started.

The API changes cover extraction inventory/copy/reconciliation/activation,
shared edits in either direction, profile adoption, affiliations, archive/restore,
merge and the reviewed Google contact-creation storage entrypoint. Base receives
CRM projection commands through root application composition. A same-DataSource
requirement makes the identity and CRM profile changes atomic. Missing links,
incorrect claims or an unavailable required consumer fail closed.

## Actual local deployment

MetaTables reported local mode, initialized/ready SQLite and DataSource
`75b7fd29-3b1f-565d-be8d-a3a27d643de2`. Base `0002` and CRM `0016` were applied
through their respective governed migration providers. Both application APIs
were stopped for inventory, copy, reconciliation and activation; the runner
also checks the application ports before writing. MetaTables stayed running.

The inventory contained **0 companies, 0 contacts and 0 affiliations**. Copy
reported zero records, and reconciliation and activation each reported zero
for all three resources. This verifies the empty local cutover; it is not evidence
of migrating a populated hosted CRM. Populated extraction was exercised with
owned fixtures in the integration suite, including retry, UUID collision,
source-version changes and historical null actor attribution.

Both APIs run locally with `CRM_BASE_ADOPTION=1`: CRM on 38641 and Base on 38651.
The CRM launcher explicitly configures local MetaTables and asserts the exact
source UUID. The single ERP frontend remains on 5175. Base readiness reports
revision `0002`, local mode and the pinned source; CRM capabilities expose adoption.

## Executed checks

| Check | Result |
| --- | --- |
| `pytest tests/erp -q` | 452 passed; existing CRM coverage includes disposable local PostgreSQL and SQLite migration/SQL tests |
| Final `pytest tests/erp/base tests/erp/crm/base_adoption -q` | 29 passed against the actual local MetaTables API, including the final affiliation archive/restore consistency check |
| Core identity integrity | Bidirectional updates, preserved Directory-only company methods, structured/unstructured names, labelled methods, exact and partial dates, stale versions and atomic rollback passed |
| Extraction | Same UUIDs, preserved provenance, repeat/collision handling, inventory fence and reconciliation passed on owned fixtures |
| Merge | Source Directory identity retained; CRM-owned affiliations, notes and structured participants moved; restart validation passed |
| Import storage | Actual GoogleStore entrypoint creates Base identity, CRM profile and source attribution atomically using a credential-free local storage fixture |
| Real HTTP identity | Local SDK-authenticated CRM adoption and Base updates passed; a supplied identity header was rejected |
| Python lint / whitespace | Ruff on changed application files and `git diff --check` passed |
| API documentation | `mkdocs build --strict` passed; mounted route index updated |
| Frontend | TypeScript/Vite, frontend unit files, documentation validation and both user-guide builds passed |
| Browser | Real local create/adopt/open/edit, stale conflict/reload, SDK shell/layout and light/dark token checks passed; details in the companion frontend report |

The full-suite run initially exposed cached catalog state leaking from real local
checks into two mocked readiness tests. The fixture now clears that cache; the
full rerun passed. The later affiliation archive/restore change was verified
with the final 29-test local suite. Deprecation warnings concern existing FastAPI
shutdown handlers and Starlette test helpers; they did not fail the checks.

Browser fixtures were explicitly owned and archived in both CRM and Directory.
Python fixtures were removed through governed commands by their recorded IDs.
No authentication or persistence mock substitutes for the local adoption evidence.
The existing regression suite still contains its established mocks and disposable
provider engines; its results are separate from the real MetaTables checks.

## Remaining release gates

The preserved compatibility columns are intentional; removing them needs a later
reviewed migration. Unrelated CRM extension operations still include PostgreSQL
queries; this work does not port every extension to SQLite. The Google fixture
verifies storage, not a live OAuth/import against Google. Shared identity merge
across modules remains a separate policy; CRM merge rejects shared affiliations
claimed by another module and retains the source person in Directory.

Before any hosted release: approve exact revisions/artifacts and module release
scope; verify Base/CRM grants, populated-data inventory and reconciliation,
write pause, production-engine operations and recovery; deploy the compatible
shared ERP artifact; verify hosted user flows. The required real-provider Tau
pre-push gate has not been run for this change because no push is being made.
Do not restart an old CRM writer with adoption disabled after cutover.

Final fresh-process check: Base `/api/base/v1/ready/` and CRM
`/api/crm/v1/readiness/` both returned HTTP 200 with `status: ready`.
CRM `/api/crm/v1/directory-adoption/` returned HTTP 200 with adoption enabled.
The final browser matrix passed all six default SDK viewports in both themes;
the combined static artifact's twelve Directory guide pages and Help round trip
also passed. The reproducible local CRM launcher is
`scripts.erp.crm.serve_local_with_base`, with a mandatory reviewed source UUID.
