# Workforce rules

An Employee is a distinct employment record for a Base person/company pair. Creating
one does not create a user, assign a Team or grant access. The pair remains unique
when archived; restore it instead of duplicating it. Person/company are immutable.
Job title, department and ordered employment dates are editable while active. Names
are captured from owners at save; changing the shared name does not rewrite history.
No private medical, financial, identity-document or payroll fields are collected.

Departments are flat and company scoped. Employee membership requires an active
same-company department. Archive requires no active members. Membership changes
fence departments, and employee commands fence the employee version. Archive/restore
retains records and does not delete or reactivate a Base person or login account.

Absence requests record inclusive calendar dates, not a working-calendar amount
or entitlement balance. Draft requests are editable. Submission freezes the saved
request; another authorized actor approves or rejects it. Approval and rejection
retain actor/time/note. Rejected and cancelled records are final. Cancellation
requires a reason; cancellation of an approved request requires manager access and
retains the original decision. There is no promise of legal leave calculation.

Submitted/approved dates must lie within employment and cannot overlap another
submitted/approved request. Every absence mutation also fences/increments its employee
aggregate, preventing races with date changes, archive and other submissions. An
employee with a submitted or current/future approved request cannot be archived.
Editing employment cannot invalidate submitted/approved dates, including history.

People read allows the bounded workforce records; write permits entry/edit/submit
and cancellation of drafts/submissions; manage permits lifecycle decisions and
cancellation of approved requests. A creator cannot approve or reject their own
request, including when also manager. This API is for authorized People staff, not
employee self-service. Base and Projects permission checks are separate.

Optional staffing requires current active employment and editable Projects work in
the same company. People passes the Base person identifier; Projects validates and
writes its assignment, task/project versions and audit. People composes that owner
plan with its employee fence/audit only on the same DataSource. Staffing does not
reserve capacity, evaluate absence against unscheduled tasks, or convert Projects
effort into payroll. Core People does not depend on Projects being installed/enabled.
