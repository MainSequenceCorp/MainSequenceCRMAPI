# Projects API contracts

Prefix `/api/projects/v1`. Identity is injected by the installed Main Sequence
middleware. Capabilities: projects.read, projects.write, projects.manage and
projects.configure. Read is required for returned records; write enables delivery
edits/effort, manage enables lifecycle/source/billing, configure exposes audit.
Hosted grants use PROJECTS_READER/WRITER/MANAGER/ADMIN_TEAM_UIDS. Local tests use
existing authenticated SDK identity and exact verified local storage.

`GET /ready/` returns local/module/revision/source, Base binding, capabilities and
sales_enabled/finance_enabled. Optional adapters are lazy and do not gate readiness.
`GET /projects/`, `/tasks/` use the normalized SDK items/pageInfo envelope with
page_index/page_size (25 default, 100 maximum), search and state. Tasks also accepts
project_uid. Unsupported queries are 422. Each collection has `/discovery/` and
`/{uid}/` detail. Project detail includes task_counts/recorded_minutes; task detail
includes project_name/project_version/project_state and recorded_minutes.

Project create POST contains request_uid, name, customer_uid,
operating_company_uid, optional description/start_date/due_date. PUT removes
request_uid and requires expected_version. Task POST contains request_uid, name,
project_uid, expected_project_version and optional description, assignee_party_uid,
due_date, estimate_minutes. PUT additionally requires expected_version. Unknown
fields are rejected. UUIDs identify records; dates use ISO date strings.

`POST /projects/{uid}/actions/{start|deliver|reopen|close|cancel}/` requires
expected_version. `POST /tasks/{uid}/state/` requires expected_version,
expected_project_version and state todo/in_progress/blocked/done/cancelled.
Completed/cancelled tasks must first reopen to todo. Completion requires active
project. Due date cannot precede a supplied project start date.

`GET /tasks/{uid}/time/` is paginated retained effort history. POST requires
request_uid, expected_task_version, expected_project_version, work_date, minutes
(strict whole integer 1–1440), description. Response is `{entry, task}`.
`GET /time-entries/{uid}/` supports uncertain-create reconciliation.
`POST /time-entries/{uid}/void/` requires expected_version, expected_task_version,
expected_project_version and reason; response is `{entry, task}`. All three
versions are fenced. Project/task version increments also receive audit events.

`GET /references/{parties|people|companies|orders}/` uses owner public collections.
`GET /sales-orders/{uid}/` verifies service-only lines through public Catalog reads.
`POST /projects/from-sales/` takes request_uid, order_uid, expected_order_version,
name and optional due_date. `POST /projects/{uid}/bill/` takes expected_version,
request_uid (Finance invoice UID), name, document_date, due_date and decimal-string
tax_rate. It returns the updated closed Project with invoice_uid/invoice_name.
The Finance adapter applies Finance validation, permissions and uniqueness rules.
Caller needs each optional owner's relevant permissions; Project access grants none.

All failures use error.code/message with 403/404/409/422/503 as appropriate; Pydantic
validation uses standard 422 detail. Uncertain creation reconciles by original UUID,
never automatic write replay. Reload after version conflict. `GET /audit/` takes
resource/record_uid and returns the latest 100 events to configure-authorized callers.

## Workforce staffing extension

Projects publishes `Service.plan_assignment(uid, person_uid, operating_company_uid,
expected_version, expected_project_version)` for the optional People integration.
It validates the caller's Projects write/read and Base read capabilities, active
Base references, same-company identity and editable project/task, then returns the
task and owner-authored guarded assignment/project/audit statements. It performs no
write itself. People composes them with its employee guard/audit in one governed
same-source transaction. No People dependency is added to Projects core or migration
history. Existing task API behavior is unchanged.
