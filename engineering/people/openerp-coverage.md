# People functionality review

Reviewed before ADR and implementation, 17 November 2026, against
`mart-e/openerp` commit `b8c8006f649f9f33f271a9dfc1434bb8ffae8798` (Odoo 14).

| Source and behavior | Bounded release decision |
| --- | --- |
| [hr_employee](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/hr/models/hr_employee.py): employee/company identity, active/archive, separate private HR and public profiles, optional user link | Employee employment record references a Base person/company, unique pair, job title, dates, own version/audit and archive. No login or access is created. Only authorized People staff see records; no sensitive private fields or public profile are collected. |
| [hr_employee_base](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/hr/models/hr_employee_base.py): department, job, manager, company, schedule and presence | Flat company departments and job-title text; staffing is an explicit optional Projects handoff using the person's Base identity. Job catalogs, managerial hierarchy, calendars and presence are deferred to People. |
| [hr_department](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/hr/models/hr_department.py): company, active flag, parent recursion prevention, members/manager | Flat departments, company compatibility and guarded archive with no active members. Hierarchy/manager propagation are deferred rather than inferred. |
| [hr_leave](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/hr_holidays/models/hr_leave.py): request dates, draft/confirm/approve/refuse, overlap prohibition, calendars, balances, two approvers | Whole-day absence requests: draft → submitted → approved/rejected; cancellation, immutable decision history, employee/date compatibility and transactional overlap guard. Inclusive calendar-day count, no entitlement or working-day deduction. Requests entered by People staff, separate approver from creator. Accruals, self-service, statutory leave, attachments and multi-stage approvals are deferred. |
| [hr_expense](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/hr_expense/models/hr_expense.py): employee reimbursement, report approval, tax/accounting and settlement | Deferred People/Finance release. Current Finance vendor bills are not presented as employee reimbursement. Payroll, recruitment, contracts and performance remain future People scope. |

Local discovery searched employee/workforce/department, leave/absence and expense/
reimbursement phrases. Existing Base identity, Projects effort and Finance payments
have different grains; none owns employment or absence approvals. New People owns
those records. Implemented/verified status is recorded in the evidence index after
execution; this initial mapping defines scope, not a parity claim.
