# Finance — step 5

The bounded Finance release is implemented and locally verified on 17 November
2026. Review → API ADR → development/docs → tests/evidence → local deployment/ops
→ companion frontend/help verification is complete. Platform release and hosted
integration remain unapproved. Later local extensions are recorded below.

- [OpenERP functionality mapping](openerp-coverage.md)
- [API ADR](adr/0001-finance-api.md)
- [Implementation and API documentation](../../docs/finance/index.md)
- [Local deployment and recovery](../../docs/finance/delivery.md)
- [Executed verification and limits](verification.md)
- [Inactive workflow candidate](deployment/finance-api.yaml.example)

Finance owns six tables, models, migration provider/version history and API.
Base is required; Sales conversion is optional and uses its public owner command
plan atomically. Customer invoices, vendor bills, observed payments, allocations,
reversals and balanced fixed-role subledger postings are implemented. This is not
full enterprise accounting parity. All omissions remain explicit in the mapping.

The paired frontend repository owns Finance screens and three user guides in the
single ERP/help artifact. Evidence: 504 backend regressions pass; real business
browser flow, six viewports/two themes, uncertain-write recovery, older allocation
history, readiness recovery, combined build, unit checks and 50-guide navigation
all pass. No platform release, hosted migration, push or tag was performed.

Inventory ADR 0001 selects the Finance-owned valuation extension in
[Finance ADR 0002](adr/0002-inventory-valuation.md). Its public posting plan and
read contracts are locally verified, including permission/duplicate refusal, zero
values and atomic compensating return. Metadata refresh used the existing Finance
provider; no revision was rewritten. The 536-test ERP regression and actual stock/
Finance browser flow pass; [Inventory evidence](../inventory/verification.md) records
execution and remaining hosted gates. No new Finance user-navigation group is needed:
the selected workflow reviews these entries in the companion Inventory detail.
