# Reporting and automation functionality review

Reviewed before ADR/development, 17 November 2026. Supplied mart-e/openerp commit
b8c8006f649f9f33f271a9dfc1434bb8ffae8798. Three natural-language local catalog searches
found existing business records and CRM campaign/transfer execution histories, but no
cross-module report definitions/snapshots or report refresh schedules. Reuse business
owners' public read contracts; keep CRM campaigns/transfers with their existing owner.

| Source inspected | Behavior | Selected adaptation |
| --- | --- | --- |
| [ir_actions_report.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/odoo/addons/base/models/ir_actions_report.py), _get_rendering_context/_render/report_action | Model-bound report definitions, user-context data, rendered outputs and saved attachments | Typed report definitions, durable versioned source snapshots, summary/detail and safe CSV export through current owner read permissions. |
| [sale_report.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/sale/report/sale_report.py), SaleReport._query | Sales dimensions, commercial amounts, delivery/invoicing measures and order reference | Sales/Finance commercial reconciliation grouped by company and currency, exact decimals and source links; separate measures for confirmed order net and posted invoice net/gross/allocation/remaining. |
| [ir_cron.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/odoo/addons/base/models/ir_cron.py), method_direct_trigger/_process_job/_process_jobs/_acquire_job | Execution user, due intervals, locking, repetitions and callback errors | Creator-scoped schedules, verified actor, guarded due claims, durable runs/steps, expiring leases, explicit failure/recovery and a separate local worker. |
| [base_automation.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/base_automation/models/base_automation.py), trigger/_process/_check | Create/update/time triggers, conditions, recursion avoidance and action execution | Fixed approved action: refresh a saved report, with progress, duplicate prevention and retained failure evidence. No arbitrary code, SQL, model hooks or owner writes. |

Second report: Operations status across Projects, Inventory movements, Purchasing and
Manufacturing. Counts are grouped by owner/status with original source links. All source
modules are optional; disabled/unavailable owners fail visibly rather than silently
omitting their data. New reporting storage never becomes a business system of record.

Deferred: arbitrary BI builder, PDF/QWeb templates, arbitrary SQL/Python/server actions,
currency conversion, statutory financial reports, warehouse-wide point-in-time snapshots,
record-change triggers, cross-user schedules/sharing, outbound notifications, external
webhooks and hosted scheduling. No Agents/MCP and no full OpenERP parity claim.

Selected adaptations above are implemented and locally verified; see [executed evidence](verification.md). Deferred capabilities remain future Reporting/automation releases; statutory reporting also requires its Finance owner. Hosted worker identity and release automation need a later reviewed deployment design and explicit approval.
