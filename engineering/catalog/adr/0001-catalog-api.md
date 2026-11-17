# ADR 0001 — Independently owned Catalog API

Date: 17 November 2026. Accepted for local implementation following the user's
instruction to continue to expansion step 3. Platform release requires explicit
approval after local verification.

## Functional basis and decision

The [OpenERP source review](../openerp-coverage.md) records the exact snapshot,
source files, chosen behavior and differences. The initial ADR/draft was started
from the general plan before the detailed comparison; that sequencing did not
meet the new review-first requirement. The comparison corrected the scope before
further implementation: categories, purchase units, reference units and rounding
increments are included in this accepted design. Future module ADRs must start
with their source review. Applied migration 0001 stays immutable; the refinements
are additive revision 0002.

Catalog owns products/services, product categories, unit groups and units. An item
is a commercial definition, not a stock balance, price, order or invoice. Sales,
Purchasing, Finance, Inventory and Manufacturing will consume its public contracts
in later stages. This release extends the API only; it adds no Agents or MCP.

Catalog needs verified platform identity and MetaTables, but no CRM or Base
business tables. It has no customer, company or currency field yet. Later Base
references must use Base's public contracts. The standalone entrypoint and module
registry declare this dependency set. Disabling API routes or frontend inclusion
preserves storage; no Catalog background job is automatically enabled.

## Owned models and migrations

Catalog uses its own SQLAlchemy metadata, namespace `erp-catalog`, physical tables
`erp_catalog__*`, provider `src.erp.catalog.migrations:migration`, provider key
`src.erp.catalog:erp-catalog`, and version table `erp_catalog__alembic_version`.
Only its migration job applies its history. Startup never migrates or seeds.

- Unit group: unique code, name and description describing compatible quantities.
- Unit: group, positive decimal factor, reference flag and positive decimal
  rounding increment. Factor means group-basis quantity per unit, inverse to
  OpenERP's stored factor. Group/factor/reference/increment are immutable. The
  first active unit is the reference, with factor one; a partial unique index
  permits at most one active reference. Other active units require it. A newly
  created group may be empty while the user adds its reference.
- Category: optional parent, acyclic hierarchy of at most 16 levels. Only a leaf
  with no children, including archived children, may move. This bounded adaptation
  avoids silently changing descendant depth; broader restructuring needs a future
  reviewed operation. Active children/items prevent archive.
- Item: unique code, name, product/service kind, required active category, default
  unit, same-group purchase unit, general/sales/purchase descriptions and sale/
  purchase availability. Omitted purchase unit selects the default on creation.
  Kind and both units are immutable; category and descriptive fields are editable.
- Audit event: verified actor, record, action, version, UTC time and changed field
  names, committed atomically with the business write.

Records have permanent UUIDs, positive versions, creator/editor timestamps and
archive state. Codes remain reserved after archive. No destructive delete API.
Foreign keys stay inside Catalog. Strict inputs reject unknown fields and binary
float quantities. Governed MetaTables transactions fence versions and references;
archive checks dependents and restore rechecks references. No direct database
connections or cross-domain writes.

Revision 0002 refuses any existing draft unit/item data instead of inventing a
reference basis or category. The actual local draft tables were empty before
application. A populated 0001 installation needs reviewed backfill work first.
Downgrade is intentionally refused: recovery uses a reviewed backup or forward
migration. Install both revisions before accepting business records.

## API and authorization

Authenticated `/api/catalog/v1` exposes readiness, resource schemas, SDK-compatible
discovery and paginated lists, detail, create, versioned replacement, archive and
restore for items, categories, units and unit-groups. Search covers name/code;
archived, item kind and unit group filters are explicit. Unsupported query fields
fail validation. See the maintained [API contract](../../../docs/catalog/api.md).

Read-only conversion computes quantity × source factor ÷ target factor using exact
integer-rational arithmetic, then rounds to a multiple of the target increment.
Compatible active units and group are required. `up` (away from zero) is the default,
matching OpenERP; `half_up` and `half_even` are explicit alternatives. Return a
fixed decimal string, rounded flag, rule/increment and both unit versions. This
is quantity conversion, not pricing or a persisted stock operation.

Main Sequence's verified User/Teams supply `catalog.read`, `catalog.write` for
items, and `catalog.configure` for reference data and audit. Configured reader,
writer and admin Teams grant progressively those capabilities; organization
admins have all. Local loopback mode grants the actual signed-in SDK user all
Catalog capabilities. It accepts no fabricated requester headers. Unconfigured
hosted users have no Catalog access. Catalog grants imply no CRM/Base access.

## Companion frontend and verification

The existing ERP static site gains a normal Catalog menu with Products and
services, Product categories, Units of measure and Unit groups. Group clicks
expand navigation; destinations change the page. SDK resource lists/details,
controls and pickers consume the API. The frontend owns interaction state and
user help; backend owns records, authorization, validation and migrations.

Frontend saves use optimistic versions. Stale/uncertain responses block blind
replay and offer reload/review; dirty navigation requires explicit discard.
Archived records are read-only and restorable subject to reference checks. Unit
details include conversion. One root build ships all ERP screens and guides.

Each stage maintains documentation alongside implementation. Verify the exact
ready MetaTables local SQLite source before migrations/mutations; exercise real
CRUD, references, rounding, permissions, audit, concurrency, repeated migration,
fresh-process binding and disabled-module behavior. Verify real browser flows,
SDK responsive/theme contracts, the combined artifact and help pages. Evidence
and production-engine limitations are recorded separately in the module index.

## Deployment boundary

The first application runs locally after explicit migration. Prepare a Catalog
migration job and separate API workflow with tag family `v<major>.<minor>.<patch>-catalog`.
Both represented resources use the same anchored promotion pattern; the API
activation depends on successful Catalog migration from its candidate image.
The [candidate](../deployment/catalog-api.yaml.example) stays outside active
workflow discovery. The ERP frontend remains one existing static-site release,
with an explicit Catalog release binding at a future approved release.

Platform validation, access review, production-engine checks, tag selection and
hosted integration remain release gates. Existing broad CRM promotion policy must
be corrected through approved work before claiming unrelated modules cannot
redeploy. No workflow reconciliation, triggering push/tag or hosted migration is
authorized by this ADR. Local SQLite success is not hosted deployment evidence.
