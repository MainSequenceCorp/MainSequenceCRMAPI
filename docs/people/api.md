# People API contract

All business routes start `/api/people/v1`. Verified SDK identity is installed once;
there are no caller-supplied user IDs. The local wrapper rejects external origins,
non-loopback clients and forged identity headers. Public `/healthz` reports process
status only. `/ready/` validates People/Base bindings and caller access; it returns
module, revision, source, capabilities, actor UID and optional integration flags.

`employees`, `departments` and `absences` provide GET collection, GET `discovery/`,
GET `{uid}/`, POST collection and PUT `{uid}/`. Collections use the pinned Command
Center `resource_collection@v1` shape (`items`, `pageInfo`) and strict discovery
shape. Queries: `page_index` 0–100000, `page_size` 1–100 (25 default), `search`
(max 200), `state`; employees/departments accept `operating_company_uid`, absences
accept `employee_uid`. Filters apply before count and page. Unknown resources 404.

All create requests require `request_uid` UUID. Updates require positive integer
`expected_version`; booleans and unknown fields are rejected. Department fields:
`name`, `description` (optional), `operating_company_uid`. Employee fields:
`person_uid`, `operating_company_uid`, nullable `department_uid`, `job_title`,
`start_date`, nullable `end_date`. Absence fields: `name`, `employee_uid`,
`start_date`, required `end_date`, plus `expected_employee_version` for both create
and update. Employee identity, department company and request employee are immutable.
Server returns full authoritative records; absence detail includes current employee
version/state and inclusive `calendar_days`; department detail includes active members.

POST `{employees|departments}/{uid}/actions/{archive|restore}/` accepts
`expected_version`. POST `absences/{uid}/actions/{submit|approve|reject|cancel}/`
accepts `expected_version`, `expected_employee_version`, `note` (max 1000).
Reject/cancel require a nonblank note. Decision actor/time cannot be supplied.
Approval/rejection by the creator is 403. Decisions retain their note when later
cancelled; cancellation stores its separate reason.

GET `references/{people|companies|departments|employees|tasks}/` returns paginated
choices through owner reads. People choices are Base persons, not organizations.
Departments/employees return active choices and support company filtering. Tasks
require enabled Projects/read access. GET `project-tasks/{uid}/` returns a task
with current parent version for staffing review.

POST `employees/{uid}/staff/` accepts `expected_version`, `task_uid`,
`expected_task_version`, `expected_project_version`. It returns `{employee,task}`
after one governed transaction. Requires People manage, Projects write/read and
Base read; foreign source, company mismatch, frozen task/project or inactive/out-of-date
employment are rejected. Projects alone authors its assignment commands. Audit records
link staffing to the target task. No foreign domain model is imported by People.

GET `{resource}/{uid}/audit/` uses the same pagination bounds and returns immutable
actor/action/version/time/field names and optional public operation lineage context.
It never exposes an unaudited mutation as success. 422 covers strict validation and
invalid references; 403 permissions; 404 missing records; 409 stale versions, duplicate
request or identity and state/business conflicts; 503 unavailable dependencies.
Do not auto-retry mutations. Read the original request UUID after uncertainty, or
reload an existing record and its affected task before considering another command.
