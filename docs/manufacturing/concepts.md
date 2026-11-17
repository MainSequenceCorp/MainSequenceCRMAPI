# Recipes, production and ownership

Manufacturing owns Bom, BomLine, Production, WorkStep and AuditEvent. Namespace
`erp-manufacturing`, own metadata and migration stream. Base owns companies/currency;
Catalog owns physical products/units; Inventory owns policies/locations/movements,
reservation balances and entries; Finance owns valuation postings. No foreign models
are imported into Manufacturing. Public owner-authored plans join guarded same-source
transactions. Every write uses the verified actor and an atomic audit record.

A BOM has one output, 1–8 distinct physical components, exact default-unit quantities
and 1–20 ordered operations. Draft can change; active freezes the recipe; archived
prevents new orders and draft reservations. Production captures active recipe/version,
scaled quantities and company/location snapshots. Fraction and unit-increment checks
reject inexact scaling. All products need active stock policies in the same company.

Production drafts cannot be edited. Cancel/recreate to change them. Reserve all inputs
atomically, then perform work steps sequentially with positive versions and explicit
nonnegative integer actual minutes/evidence. Completion requires every step done and
consumes/produces the whole batch atomically. Cancel draft or reserved orders only,
releasing all inputs before work begins. Started/completed batches cannot be reversed
in this scope. Inventory's individual actions reject coordinated production movements.

Optional Finance handoff uses each movement's fixed standard cost; full batch posting
is atomic and once-only. Failures leave physical completion intact and all unposted
flags unchanged. No actual costing, labor capitalization, overhead allocation or
manufacturing profit calculation. No MRP scheduler, work center capacity, recursive
BOM, procurement automation, partial output, scrap, by-products, lots or disassembly.
