# People API

People maintains employee, department and absence records independently of platform
login identities and CRM. Base supplies shared person and company identity. Its
four models belong to its own migration provider; optional Projects staffing uses
an owner-authored operation. No new Agent or MCP is included.

- [Workforce concepts](concepts.md)
- [API contracts](api.md)
- [Local delivery and recovery](delivery.md)

This bounded release includes workforce records and whole-day absence approval.
Payroll, balances/accruals, working calendars, private HR information, self-service,
recruitment and expense reimbursement are outside this release. Evidence and the
OpenERP mapping live in `engineering/people` in the repository.
