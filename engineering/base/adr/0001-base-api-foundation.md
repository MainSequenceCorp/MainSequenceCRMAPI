# ADR 0001: ERP Base API foundation

Date: 17 November 2026. Status: implementation decision for expansion step 1;
platform release requires explicit user approval after local verification.

## Problem and scope

Future modules need shared business identities and reference data without
depending on CRM's prospecting model or migration history. Build ERP Base as an
independent API module in this repository, with companion Business Directory screens
in the one ERP static site maintained in the existing frontend repository. No CRM data moves in this step.

This ADR covers backend API extension, persistent models, migration ownership,
authorization, concurrency, compatibility and local delivery. New Agents and MCP
tools are excluded. Frontend screen composition remains frontend-owned.

## Ownership and boundaries

Base owns people and organization parties, dated person-to-organization
affiliations, addresses, operating companies, countries/subdivisions, languages,
currency definitions and rounding, user locale preferences, shared defaults and
number sequences. An operating company references an organization party; it is
not a Main Sequence Organization or Environment. A person party is not a login.

CRM retains its current models, records, identifiers, routes and migration
provider. Step 2 will define the controlled extraction into Base. Base has no
imports from CRM and no foreign keys to CRM tables. Finance will own exchange
rates, banking, taxes and legal document issuance. Base numbering is an allocator;
it does not promise gapless legal numbering or document issuance.

Explicit module registration identifies Base, its API prefix, provider and empty
prerequisite set. Enablement controls mounting, not record deletion. Unknown
modules or missing prerequisites fail composition. Identity and transport remain
technical infrastructure; there is no new application user/role database.

## Models and migrations

Use `src/erp/base/metatables/` with separate SQLAlchemy metadata. Register an
explicit model list through `src.erp.base.migrations:migration`, namespace
`erp-base`, physical prefix `erp_base__`, and version table
`erp_base__alembic_version`. Revisions live under that provider. Never add Base
models to CRM metadata or amend applied CRM revisions.

Each mutable record has a stable UUID, positive edit version, UTC creation/edit
times, verified actor identifiers and a soft archive marker. Reference codes
are unique and immutable once created. Database constraints enforce keys,
relationships, valid enumerations and positive counters. The API enforces
additional typed rules and active-reference requirements. Store audit events
in Base's own append-only stream in the same transaction as each mutation.
No destructive delete or party merge is exposed in this first release.

Reference datasets are operator-managed records. Ship a small, explicitly
labelled starter set (AT/DE/GB/US, English/German/Spanish/French/Italian,
EUR/USD/GBP/JPY); it is not an exhaustive world or legal reference database.
Seeding is an explicit command after migration, uses stable UUIDs, preserves
operator edits and is repeatable. No migrations, seed data or network writes
run at module import or application startup.

## API contracts

The independently launched FastAPI application uses `/api/base/v1/`. Resource
collections provide bounded pagination, deterministic ordering, search, active
or archived filtering, details, strict typed create and full replacement update.
Updates and archive/restore require the expected record version. A stale version
returns 409 without changing data or audit. Unknown fields are rejected.

Each resource exposes `/discovery/` conforming to
`command-center.resource_discovery@v1`; collections conform to
`command-center.resource_collection@v1` at the adapter boundary. Contract
authority is the companion frontend's pinned Command Center SDK 0.5.19 manifest,
schemas and indexed fixtures, verified byte-for-byte against source commit
`4cb4d457c2780c6ca813026cca97fe642113f9b4`. Pinned portable fixtures and
provenance live in `tests/erp/base/contracts/sdk-0.5.19/`. Detail, create/update, archive, preferences,
number allocation, readiness and module-registration responses are explicit
application contracts documented by OpenAPI. They do not claim unrelated SDK
wire contracts. No bulk operations are advertised in this release.

Collections: parties, affiliations, addresses, operating-companies, countries,
subdivisions, languages, currencies and number-sequences. Settings is a typed
singleton; preferences are scoped to the verified actor, with no endpoint to
read or edit another user's preferences. Audits are read-only to administrators.
Number allocation accepts a caller-supplied request UUID and an expected sequence
version, records a durable allocation and increments the counter atomically.
Retrying the same request returns its original allocation; reuse against a
different sequence is a conflict. Allocation results preserve the issued prefix,
number and rendering even after configuration changes.

Use bounded decimal strings for rounding APIs and Python Decimal arithmetic;
currency precision and rounding mode are validated server-side. No exchange-rate
conversion is offered. Locale/timezone values use explicit stored references
and the standard timezone database; UI translations remain frontend-owned.

## Identity, permissions and integrity

Install Main Sequence request identity once, after mounting routes. Resolve the
effective actor from the verified requester, otherwise the verified caller.
Never trust user-ID headers or fall back to the workload identity for a failed
requester. Existing platform Teams supply Base reader, writer and administrator
permissions; Base access grants no access to another module's business records.

Readers may inspect shared records and maintain their own preferences. Writers
may manage parties, affiliations and addresses. Administrators additionally
manage reference data, operating-company configuration, defaults and numbering.
Organization administrators can administer Base. Shared configuration uses
separate permissions from ordinary party editing. Storage grants for a future
hosted workload remain distinct from these application permissions.

The local launcher is loopback-only and uses the existing SDK-authenticated
developer. It rejects externally supplied identity headers and non-loopback
Origin/Host values. Local mode never bypasses SDK sign-in or runtime verification.
The deployed entrypoint does not enable local impersonation.

All routine storage operations use the MetaTables client and governed SQL API.
Use parameterized SQLAlchemy statements and guarded atomic statement lists for
version checks, reference checks, record mutation and audit. Active references
must still exist when a command commits. Archive blocks while active dependents
need the record. Stable identities and preserved historical references allow
later CRM extraction. Invalid references, conflicts and denial have explicit
public errors; SQL, connection details and credentials are not returned.

## Local delivery and future release

Before writes, verify `local_mode: true`, SQLite, ready initialization and the
expected local DataSource. Bind every Base table to that source and provider.
Apply and repeat Base migrations through the local MetaTables API; prove schema
independence, CRUD, permissions, conflicts, archive guards, atomic allocation,
audit, reference seeding and persistence across fresh processes. Start the API
and companion frontend locally and verify actual user flows together.

The future platform deployment unit is a Base-only API entrypoint and its own
migration Job, selected by a Base workflow and `v<major>.<minor>.<patch>-base`
tags. Base has no CRM runtime prerequisite. Business Directory joins the shared
ERP frontend artifact and UI release; it has no separate static-site resource or
build root. Candidate deployment declarations stay outside the active workflow
directory until approval and backend validation; no push, release tag or
platform reconciliation is authorized by this ADR. Platform ownership/Team
setup, exact workflow validation and production-engine behavior must be checked
before requesting deployment approval.

## Acceptance and stopping point

Base installs and runs without importing CRM. Its independent migration stream
and local API/frontend must pass their recorded checks. Disabled Base mounts no
business routes and preserves storage. Existing CRM tests remain passing.
Record local evidence and limitations in `engineering/base/verification.md`.
Do not start CRM extraction or another module. Without platform approval, report
Base as locally verified with its hosted completion gates still open.
