# People local verification

17 November 2026. Source review and API ADR preceded development. Actual runtime
reports local true, SQLite, active/ready bootstrap and exact DataSource
`75b7fd29-3b1f-565d-be8d-a3a27d643de2`. Source is rechecked before migrations and
mutations. No hosted fallback or application database engine was used.

## Ownership and local deployment

Official MetaTables scaffold/revision creates four People tables and its independent
version table/provider, namespace `erp-people`, revision 0001. Revision was reviewed
and formatted before application and remains immutable. Repeat migration preserves
Base/Projects/Finance revision bindings; a fresh API import does not import CRM,
Projects, Finance, Sales or Catalog. Fresh-process reads retain saved employment.
Core API serves employees with Projects disabled and rejects staffing references.
People metadata/column rules pass; two semantic queries per model find each owner
among the first five results after catalog finalization.

The independent API runs locally on 38701 with actual SDK sign-in and exact source
validation. Ready includes People/Base bindings and effective permissions. External
origins and forged caller headers are denied. Disabled API factory has no business
routes. Neither API imports nor startup apply migrations. Companion Vite transport
is `/api/people`, separate from every other module.

## Executed backend evidence

Six focused integration tests passed (one existing warning, 10.45 seconds). The
complete ERP suite passed **518 tests**, with 41 existing deprecation warnings in
135.63 seconds. A subsequent stronger API import/disablement/restart/contract test
passed separately (8.80 seconds); no business code changed after the complete run.

Executed scenarios include person/company uniqueness, immutable identity, company-
scoped departments, membership archive protection, ordered employment/absence dates,
version conflicts, atomic audit rollback, permission refusal, draft/submit/approve/
reject/cancel history, separate creator/approver, overlap rejection, concurrent
submissions with one winner, and archive/date changes fenced against absence.
Staffing checks independent operation without Projects, separate Projects permissions,
same-company matching, stale owner-plan rollback and successful traced assignment.
Actual authenticated HTTP validates pinned SDK collection/discovery schemas and strict
payloads. Policy-specific actors are explicit fixture UUIDs, not claimed as separately
authenticated accounts. Browser approval below uses real SDK identity.

## Browser and frontend evidence

Real Chrome/local API workflows pass department/employee creation, field updates,
a concurrent edit followed by stale failure/reload, unsaved-navigation protection,
whole-day absence creation/submission, creator exclusion from decisions, actual
approval of another policy fixture actor's request, retained decision after reasoned
cancellation, department/employee archive/restore, and Projects staffing with read-back.
Opening the resulting task verifies the companion Projects screen.

During independent People work, browser calls to CRM/Base/Catalog/Sales/Finance/
Projects were blocked; no such call occurred before deliberate cross-module navigation.
A real department POST was committed and its response deliberately aborted. GET of
the original UUID recovered the record with exactly one POST and no mutation replay.
Keyboard picker selection and all six SDK layout viewports in light/dark pass; final
screenshots wait for reference labels to load and the 375px capture was inspected.

The first browser run found a test selector that included a required-field marker;
the next exposed a picker popup behind a confirmation dialog. Staffing selection
now lives on the employee page, with the dialog solely confirming the reviewed task.
The full browser run passed after that fix. Held/failed readiness and explicit Retry
also pass. Nine frontend unit files, TypeScript, theme audit, docs validation and
combined Vite/Docusaurus build pass. Build retains existing chunk-size/update-check
notices. Strict People and Projects API MkDocs builds pass. All 57 built guides pass desktop/mobile, light/dark, shared General/Modules order,
links and unsaved navigation. Existing CRM/Directory/Settings navigation, history,
reload and mobile checks pass. People feature Help round-trips are checked separately.

## Reproduction and remaining gates

Use `docs/people/delivery.md` for source, environment, test and launch commands. All
fixtures are local and owned UUIDs, cleaned after the check. Earlier CRM regressions
still use their existing PostgreSQL compatibility fixtures; new People writes use
MetaTables Local SQLite. The paired frontend evidence index lists build/browser commands.

SQLite does not prove production-engine concurrency or hosted policy. Team/namespace
ownership, workload membership, cross-owner access, resource bindings, production
checks and approval remain gates. The People workflow example is inert and unvalidated
on the platform. No push, release tag, workflow activation or hosted migration occurred.
This bounded release does not claim full OpenERP HR parity; source mapping records
private HR, payroll, accrual/calendar, self-service and expense gaps for future People.
