# ERP Base maintenance

Expansion step 1 implements the shared business foundation. Its API decision is
[ADR 0001](adr/0001-base-api-foundation.md); evidence and remaining release gates
are in [verification](verification.md). The user has now authorized CRM extraction as step 2 locally, under its separate API ADR.

## Ownership

| Concern | Base-owned location |
| --- | --- |
| Thirteen storage models and independent metadata | `src/erp/base/metatables/` |
| Migration provider and frozen revisions | `src/erp/base/migrations/` |
| Typed inputs, commands, seeding and governed persistence | `src/erp/base/` |
| HTTP routes and existing platform identity integration | `api/erp/base/` |
| Explicit local setup and future migration Job entrypoint | `scripts/erp/base/`, `jobs/erp/base/` |
| Local integration tests and pinned SDK contract fixtures | `tests/erp/base/` |
| Technical module registration only | `src/erp/modules.py` |

Base owns eleven editable resources plus immutable number allocations and audit
events. Its provider is `src.erp.base.migrations:migration`, namespace `erp-base`,
table prefix `erp_base__`, and version table `erp_base__alembic_version`.
Do not import CRM, add Base tables to another module's metadata, modify an applied
revision, or create tables at startup. Subsequent schema changes require a new
Base revision and an updated readiness expectation.

Business Directory is the user-facing module in the companion repository under
`src/erp/base/`, `docs/base/` and `documentation/base/`. It shares one ERP static
site, root build and main left navigation with CRM and future modules. Its
editor consumes API input schemas and capabilities;
its types and forms do not own storage. No Agent or MCP surface is introduced.

## Local setup and first run

Use the existing SDK sign-in. From this repository, in separate terminals where
the command remains running:

```bash
.venv/bin/metatables serve --local --no-open-browser
.venv/bin/metatables --local runtime status
```

If the runtime explicitly reports pending local initialization, run
`.venv/bin/metatables --local runtime initialize`, then inspect status again.
Require `local_mode: true`, SQLite, ready bootstrap and the expected local
DataSource before any writes. The setup command repeats those checks and fails
closed; it never switches to hosted discovery.

```bash
.venv/bin/python -m scripts.erp.base.setup_local
.venv/bin/python -m uvicorn api.erp.base.local:create_app --factory --host 127.0.0.1 --port 38651
```

Setup applies only Base's provider and explicitly seeds shared defaults and a
small starter set: four countries, five languages and four currencies. It
preserves existing operator edits. It does not migrate or seed CRM. The local
launcher verifies the existing SDK identity and rejects external origins,
non-loopback callers and supplied identity headers. Never expose it publicly.

From the companion frontend repository with Node 24, run `npm run dev`.
The application listens on `http://127.0.0.1:5175/` and proxies Base requests to
port 38651. CRM uses its separate local API on port 38641. The one root
`npm run build` artifact contains both modules and their user guides; Business
Directory help is at `/docs/directory/`. Follow the companion engineering guide.

## API use and integrity

The prefix is `/api/base/v1/`; interactive OpenAPI is available at `/docs` on
the local API port. `ready/` verifies catalog ownership and initialized defaults;
`catalog/` publishes editable schemas and permission-derived capabilities.

| Resource | Responsibility |
| --- | --- |
| `parties` | People and organizations, contact details, preferred language |
| `affiliations` | Dated person-to-organization relationships and roles |
| `addresses` | Party addresses with country/subdivision consistency |
| `operating-companies` | Organization-backed operating entities and acyclic hierarchy |
| `countries`, `subdivisions`, `languages`, `currencies` | Managed reference definitions; currency precision and rounding |
| `settings` | One shared defaults record |
| `preferences` | One private preferences record for the verified requester |
| `number-sequences` | Configured number allocation, optionally scoped to an operating company |

Every resource has list, discovery, detail, create and full update routes.
Updates require `expected_version`; archive/restore use separate POST commands.
Defaults and preferences cannot be archived. Codes, party kind, a company's
party and a sequence's company are immutable. Parent hierarchies are bounded to
16 levels. Archived or incompatible references cannot be attached. Archival of
a referenced record fails atomically while active dependents require it.

`POST number-sequences/{uid}/allocate/` accepts `request_uid` and
`expected_version`. Persist/reuse the same request UUID after an uncertain
response; concurrent retries return the original allocation once committed.
A different actor or sequence cannot reuse that request. Only allocation can
advance the counter. Numbering does not issue documents or promise gapless legal
numbering. `POST currencies/{uid}/round/` takes a decimal string `amount`.
No FX conversion or Finance behavior belongs here.

Readers manage only their own preferences; writers also manage parties,
affiliations and addresses and allocate numbers. Administrators manage reference
data, companies, defaults and sequence configuration and read `audit/` by record
UUID. Future hosted grants use existing platform Teams through
`BASE_READER_TEAM_UIDS`, `BASE_WRITER_TEAM_UIDS` and `BASE_ADMIN_TEAM_UIDS`.
Application permissions and workload storage grants must both be verified before
a platform release. The local developer receives Base capabilities only after
SDK identity verification.

Storage commands use parameterized SQLAlchemy compiled through MetaTables.
Writes, version/reference guards and audit are atomic. Audit stores changed
field names, actor, time and version, not a second copy of personal values.
There is no destructive delete, merge or CRM transfer endpoint in step 1.

## Verification and release discipline

```bash
.venv/bin/pytest tests/erp/base -q
.venv/bin/ruff check src/erp/base api/erp/base scripts/erp/base jobs/erp/base tests/erp/base src/erp/modules.py
```

Tests use the real, initialized local MetaTables API and verify its runtime
before migrations and writes. Python fixtures delete only their own explicit
test IDs through governed commands. Browser fixtures remain archived locally.
Do not replace this evidence with mocked authentication or remote fixtures.

No Base declaration is installed under `.mainsequence/workflows/`. A future
Base-only workflow must pair its API with its own migration Job and select only
Base release tags. The companion repository retains one shared ERP artifact and
workflow, released with an ERP UI tag only when its code/configuration changes.
Prepare and validate that exact release and production-engine behavior before
requesting user approval. No triggering push, tag, hosted migration or platform
deployment is permitted until explicitly approved. Local verification does not
close the hosted integration gate. The subsequent user instruction authorizes step 2 locally only.


After CRM adoption is activated, launch Base with `CRM_BASE_ADOPTION=1` and
use the CRM `scripts.erp.crm.serve_local_with_base` launcher with the reviewed
source UUID. The [step-2 local procedure](../../docs/crm/delivery/base-adoption.md)
supersedes the independent step-1 launch commands for that activated source.
