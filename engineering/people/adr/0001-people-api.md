# ADR 0001 — Independent People API

Accepted for local implementation, 17 November 2026, after the
[functionality review](../openerp-coverage.md). No new Agents or MCP.

## Ownership and foundation

People owns Department, Employee, AbsenceRequest and AuditEvent, its SQLAlchemy
metadata, `erp-people` namespace/provider and `erp_people__alembic_version`. Base
is the only required module. Employee UID denotes employment, never a platform
user; person and company are immutable Base references. A person/company pair is
unique, including archived employment; restore the existing record. Departments
are flat, company scoped and cannot be archived with active employees. Private
HR data, payroll and employee-to-user linking are excluded.

## Operations, identity and concurrency

`/api/people/v1` exposes normalized SDK discovery/collections/details, create/update
commands for departments/employees/absence requests, explicit archive/restore and
submit/approve/reject/cancel commands, audit history, Base references and readiness.
Use strict payloads, supplied request UUIDs and expected record versions. Creation
uncertainty is resolved by GET of that UUID; no automatic command replay.

Verified injected identity/Teams grant `people.read`, `people.write`, `people.manage`
and `people.configure`. Read permits all bounded workforce records; writer maintains
records and requests; manager handles archive/restore and decisions. Approver must
be different from the request creator. There is no unverified employee self-service.
People access never grants Projects or Base access. Invalid references return 422,
missing records 404, denied operations 403, stale/duplicate/state conflicts 409.

Employment start/end must be ordered; approved/submitted absence must fit employment
and cannot overlap another submitted/approved request. Absence uses inclusive calendar
dates, not working-day entitlement. Requests freeze on submission. Rejected/cancelled
requests are retained and final; a new request has its own identity. Employee edits
and absence commands fence the employee aggregate, preventing races with archive or
incompatible dates. Department membership/employee lifecycle changes fence affected
departments. Each transaction includes audit; no silent partial change.

## Selected integration

Optional staffing assigns an active employee's Base person to an editable Projects
task in the same operating company. It requires People manage and the caller's
Projects write/Base read permissions. Projects publishes an owner-authored command
plan with task/project fences and audit; People composes that with its employee
version fence and audit in one same-source governed transaction. No People code
imports or writes Projects models. The API works without Projects when disabled.
Projects effort remains delivery effort, not payroll or People timesheets. Staffing
does not promise availability scheduling or check leave against unscheduled work.

## Delivery and verification

Apply only the own provider to the exact ready local SQLite source. No import/startup
migrations. Test isolation/restart, actual authenticated contracts, business commands,
version races, rollback and optional staffing. Companion shared ERP UI adds People
with Employees, Departments and Absence requests; shared guide/sidebar, unsaved edits,
error recovery, narrow screens and both themes are verified against local APIs.
Document every stage. An inert `-people` workflow candidate/migration Job is prepared;
platform grants, production concurrency, release bindings, push/tag/activation require
explicit approval. No hosted action is part of this decision.
