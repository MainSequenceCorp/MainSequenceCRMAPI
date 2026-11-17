# People — step 7

The local cycle is verified: source review, API ADR, implementation/docs, 518 passing
backend tests, local deployment and companion frontend/help/browser checks.
Collaboration is next in the authorized sequence. Platform release is unapproved.

- [OpenERP functionality review](openerp-coverage.md)
- [API ADR](adr/0001-people-api.md)
- [Concepts and API](../../docs/people/index.md)
- [Local setup and recovery](../../docs/people/delivery.md)
- [Executed evidence and limits](verification.md)
- [Inactive workflow candidate](deployment/people-api.yaml.example)

People owns its Department, Employee, AbsenceRequest and AuditEvent models, own
migration provider/version table and API. Base is required; Projects staffing is
optional and permission checked through its public owner plan. Frontend/help live
inside the one shared ERP static artifact. Detailed gaps remain explicit; no Agent/MCP.
