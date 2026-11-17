# ADR 0001 — Sales quotations and orders API

17 November 2026. Accepted for local implementation following the
[source review](../openerp-coverage.md). Hosted deployment awaits user approval.

## Scope and ownership

Sales owns quotation/order aggregates, ordered line snapshots, edit versions and
audit events. Use separate metadata, namespace `erp-sales`, physical prefix
`erp_sales__`, provider `src.erp.sales.migrations:migration` and version table
`erp_sales__alembic_version`. No Base, Catalog or CRM migration is changed.
Base and Catalog are declared prerequisites; consume their public service read
contracts and permission policies. CRM is optional. No new Agent/MCP work.

## Contracts and rules

`/api/sales/v1/orders/` provides paginated search/state-filtered collections,
discovery, detail, create, full draft replacement and explicit quoted/confirm/
cancel/reopen commands. Inputs reject unknown fields and malformed decimal
strings. Every update/action requires the expected aggregate version. Creation
requires a client request UUID used as the record UID; after an uncertain result,
read that UID before retrying. Existing UUIDs and unique business references
conflict rather than silently overwriting or duplicating records.

An order has a customer, company, currency, optional expiry/customer reference,
terms and up to 100 lines. Each line has a Catalog item, its default unit,
description, positive quantity, nonnegative unit price and discount in [0,100].
Use Decimal arithmetic and the Base currency's precision/rounding; persist
amounts as decimal strings. Sum rounded line net amounts. No tax/FX calculation.
Currency, customer, company, product and unit names/versions are snapshotted at
draft save. Confirmation revalidates active references and refreshes snapshots,
requires at least one line and an unexpired quotation. Confirmed terms are
immutable; downstream consumers receive that stable aggregate through Sales.
Cross-module reads are point-in-time snapshots, not distributed transactions.

Atomic governed transactions fence the parent version/state, replace draft
lines and append audit together. Confirmed lines retain stable identifiers.
No destructive API delete. Cancellation preserves history and rejects registered
downstream usage. A Sales-owned linking command with expected version and a
unique consumer reference is the only way later integrations attach their
results; separate authorization is required for the owning integration.

Collections/discovery use the portable Command Center resource contracts pinned
in the existing fixture pack, SDK 0.5.19, source commit
`4cb4d457c2780c6ca813026cca97fe642113f9b4`. Strict command/detail/reference/readiness
payloads are application-owned OpenAPI contracts. Base/Catalog reference pickers
return normalized collections after their own read authorization. CRM lookup is
explicitly optional; local verification uses its authenticated loopback API.
Hosted CRM transport is unavailable until separately configured and verified.

## Identity and permission boundaries

Use installed request identity once and verified requester/caller. Sales read,
write and configure capabilities use existing platform Teams; configure controls
audit access. Cross-module reads additionally require those modules' read
capabilities. The loopback launcher checks the exact ready SQLite source and
uses existing SDK sign-in; it rejects external origins and injected identity.
No migrations at import/startup and no hosted fallback from local mode.

## Delivery and evidence

Verify schema constraints, migration repetition and isolation, fresh-process
persistence, Decimal boundaries, invalid references, permissions, lifecycle,
expiry, stale/concurrent writes and audit rollback. Validate actual HTTP
collections/discovery against the pinned schemas. Run the first API locally on
38671, then verify the companion frontend and actual API together, including
CRM-independent operation, optional linkage, dirty/conflict recovery and mobile.
Ship the module guide inside the one General/Modules documentation site. Keep
backend operations/documentation and frontend implementation evidence separate.
Only after this local cycle may Finance begin. No push, release tag, workflow
activation, hosted migration or platform deployment is authorized by this ADR.
