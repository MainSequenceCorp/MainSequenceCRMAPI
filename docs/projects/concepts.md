# Delivery concepts and rules

Project owns customer/company/date context, delivery state, commercial source and
invoice trace. DeliveryTask belongs to one immutable project and carries work
expectations, optional Base-person assignment, deadline and whole-minute estimate.
TimeEntry is append-only effort with recorded/voided state, reason and actor.
AuditEvent commits with every operation. Each provider table has descriptive metadata,
namespace `erp-projects`, independent version table and revision 0001.

Planned projects start active. Delivery requires at least one done task, with all
other tasks done or cancelled. Delivered projects freeze tasks/effort until reopened
while unbilled. Closing or cancelling is final; cancellation requires no open tasks.
Task creation/edit/state and time append/void fence and increment the project
version. Delivery racing new work therefore cannot miss that work. Task changes
also fence their own version. All same-owner changes and audit are atomic.

Effort is 1–1440 whole minutes per entry, dated no later than today. Only active
project effort can change; cancelled tasks reject effort. An entry's creator or a
Projects manager may void it. Minutes do not determine invoice totals or payroll.
No new employee/platform-user model is created.

Optional service-order conversion accepts only confirmed service-only orders,
creates one project and one task per line, and retains unique source identities.
Sales owns the downstream link and publishes its authorized transaction plan.
Quantity units are not guessed as hours. Mixed goods/services and multiple projects
per order are deferred. Catalog is only needed by this optional adapter.

After delivery, the billing command calls Finance's public owner-authored
`plan_from_sales`. Invoice creation, the Sales link, Projects closure/invoice link
and audits commit atomically on the same governed DataSource. An already invoiced
order conflicts without partially closing the project. Invoice posting/payment
remain Finance operations. No Projects code imports foreign table models.
