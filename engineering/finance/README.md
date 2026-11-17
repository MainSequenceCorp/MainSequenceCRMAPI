# Finance — step 5

The bounded Finance release is implemented and locally verified on 17 November
2026. Review → API ADR → development/docs → tests/evidence → local deployment/ops
→ companion frontend/help verification is complete. Platform release and hosted
integration remain unapproved. Projects and services is next in the local sequence.

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
