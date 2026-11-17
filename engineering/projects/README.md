# Projects and services — step 6

The full local cycle is verified: review, API ADR, implementation/docs, 512 passing
backend tests, local deployment and companion frontend/help/browser integration.
Platform release remains unapproved. People is next in the authorized sequence.

- [OpenERP source mapping](openerp-coverage.md)
- [API ADR](adr/0001-projects-api.md)
- [Concepts and API](../../docs/projects/index.md)
- [Local operations](../../docs/projects/delivery.md)
- [Executed evidence and limits](verification.md)
- [Inactive workflow candidate](deployment/projects-api.yaml.example)

Projects owns four models/tables and its own migrations. Base supplies identity
records. Optional public-owner integrations connect Sales service orders and Finance
billing. CRM follow-up tasks remain unchanged. The paired frontend owns Projects,
Delivery tasks and three guides inside the one shared ERP/help artifact. All stages
must be verified before proceeding to People; no hosted gate is waived.
