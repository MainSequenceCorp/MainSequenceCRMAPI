# ADR 0001: independent Manufacturing API and full-batch production

Accepted for local implementation, 17 November 2026, after the recorded
[OpenERP source review](../openerp-coverage.md). API extension only; no new Agents/MCP.

Manufacturing owns BOM, BOMLine, Production, WorkStep and AuditEvent, with separate
metadata, namespace erp-manufacturing, provider/history/version table. Base, Catalog
and Inventory are explicit prerequisites; Finance is an optional Inventory-owned
handoff. Purchasing is an independent replenishment option, not a dependency.

A draft BOM contains one physical output quantity in its Catalog default unit,
1–8 unique physical components in their default units, and 1–20 ordered operation
names. Output cannot be its own component. Activate freezes a validated revision;
archive prevents new orders but preserves existing snapshots/history. Changes require
a new BOM draft. No recursive explosion: manufactured components are ordinary stocked
inputs. Exact decimals and unit increments are required; no silent rounding.

Creating a production order freezes one active BOM/version, output quantity, scaled
component quantities, one company, raw/finished internal locations and a virtual
production location. All products require Inventory stock policies in that company.
The draft is immutable; cancel and create a reviewed replacement to change inputs.
Reserve atomically claims every component and creates Inventory-owned ready movements
through a complete public plan. Recheck current BOM and policy/location eligibility.
Insufficient stock or any stale guard rolls the entire plan back. Concurrent jobs
cannot reserve the same available quantity.

Manufacturing owns sequential work steps. Start the next pending step only after its
predecessor is done; complete a started step with nonnegative bounded actual minutes
and evidence. Order/step versions serialize updates. All steps must finish before
full batch completion. Inventory then consumes every reserved component and produces
the complete output in one transaction with Manufacturing's state/audit. Cancel only
draft/ready orders (before work begins), releasing all reservations. Completed batches
are retained; no automatic disassembly or partial cancellation in this release.

Inventory's production movements are coordinated records: ordinary individual
transition/return/Finance endpoints refuse them, preventing partial side effects.
Manufacturing never imports foreign models. Public owner-authored batch plans join
same-source guarded transactions. Inventory groups stock/configuration fences and
multirow inserts; eight components plus output fit the SDK's 32-statement budget,
including full Finance handoff (at most 22 statements). Test the maximum size.

After completion, optionally post all component/output standard-cost valuations to
Finance atomically via Inventory. Require Finance post permission independently.
Expose source movement entries and each consumed/output value. Net difference
is a fixed-standard-cost comparison, not actual production profit/cost or labor. No
Finance DDL required. A failed financial handoff leaves the completed physical batch
and all unposted flags unchanged; a successful handoff cannot repeat.

HTTP prefix /api/manufacturing/v1: ready/resources/discovery/collections/detail,
BOM draft create/update/activate/archive, production create/reserve/cancel/complete,
work-step start/finish, valuation handoff/read, audit and public prerequisite pickers.
Strict payloads, injected identity manufacturing.read/write/manage/configure, separate
Inventory/Finance permissions, current versions and atomic audit. Local requests use
the existing SDK sign-in; original creation UUID lookup handles uncertain results.

Required evidence: actual verified Local SQLite source; own migrations/repeated setup,
scaling/limits, maximum-size stock/Finance transactions, reservation races, stale rollback,
operation order, cancellation, reconciliation, owner permissions, disabled Finance,
fresh imports and authenticated pinned SDK HTTP contracts. Deploy locally, integrate
companion screens and three guides in the single ERP artifact, verify browser/theme/
responsive/dirty/conflict/uncertain flows and General → Modules navigation before the
next module. Platform migration/deployment requires separate explicit user approval.
