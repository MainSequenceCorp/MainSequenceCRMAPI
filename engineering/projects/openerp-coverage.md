# Projects and services functionality review

Reviewed 17 November 2026, before ADR and code, at OpenERP/Odoo 14 commit
`b8c8006f649f9f33f271a9dfc1434bb8ffae8798` in `mart-e/openerp`.

| Source and observed behavior | Selected adaptation / later owner |
| --- | --- |
| [project.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/project/models/project.py): projects have customer, company, dates, project manager, tasks; tasks have stages, deadlines, assignees, planned hours and completion. | Projects owns project aggregates, delivery tasks, dates, Base customer/company and optional person assignments. Fixed task states replace configurable Kanban stages initially. CRM follow-ups remain CRM-owned. |
| Same source: privacy/portal audience, recurring tasks, subtasks, templates, ratings and email aliases. | Internal capability-controlled module only. Portal belongs to Website; configurable stages, recurrence, nested tasks, ratings and templates are later Projects releases; no implicit sharing from a project link. |
| [sale_project sale_order.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/sale_project/models/sale_order.py): `_timesheet_service_generation`, project/task creation from service lines, source-line links, duplicate prevention. | Optional explicit confirmed service-only order → one project, one task per line. Source quantities are not silently converted to hours. Historical source association remains unique even if cancelled. |
| [sale_timesheet project.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/sale_timesheet/models/project.py): billable project/task mapping, service-only constraint, project or employee rates, uninvoiced timesheets. | First release records exact whole-minute effort on delivery tasks, with creator and reversible history. No employee/payroll model or rate inference. Employee-rate and time-based billing deferred to Projects/People/Finance integration. |
| [sale_timesheet sale_order.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/sale_timesheet/models/sale_order.py): timesheet-delivered quantities and invoice preparation. | Explicit full fixed-price invoice handoff only after all noncancelled delivery tasks finish. Finance owns invoice construction/posting/payment; Projects holds the delivery trace. Partial/milestone/time billing deferred. |

Three verified-local MetaTable searches for delivery projects, billable work and
milestones returned CRM follow-ups/campaign tasks, finance lines and market-calendar
records, with different grain. No existing service-delivery project owner was found.
New storage must not reuse CRM task rows. Source inspection is not an Odoo parity test.
Status is pending implementation/verification; this mapping defines the bounded scope.
