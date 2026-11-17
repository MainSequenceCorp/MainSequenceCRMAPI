# Marketing local verification — 17 November 2026

Local cycle verified; platform release unapproved. The source review and API ADR
preceded implementation. Capture-only delivery and simulated engagement remain
explicit local adaptations, not evidence of real email delivery or OpenERP parity.

## Backend, ownership and runtime

Actual MetaTables Local: local_mode true, SQLite, active/ready bootstrap and exact
source `75b7fd29-3b1f-565d-be8d-a3a27d643de2`. Own five-model provider applied reviewed
revision 0001, namespace erp-marketing and version table erp_marketing__alembic_version.
Applied migration remains unchanged. Repeated upgrade, owner isolation, wrong-source
refusal, independent API import and fresh-process persistence pass. Base is the sole
prerequisite; CRM can be disabled without blocking mailings. API runs on loopback
38721 with the actual SDK identity. New mutation tests use actual Local SQLite;
legacy CRM regression also exercises its established local PostgreSQL fixtures.

Six core tests passed (14.13s); optional actual CRM read/link test passed (6.74s).
Full ERP regression: **530 passed**, 41 existing warnings, 168.55s. Covers strict
payloads, positive version fences, identity forgery refusal, HTTP authentication and
hostile origins, normalized subscription uniqueness, current Base email membership,
withdrawal/resubscribe evidence, content/audience freeze, retained snapshots,
suppression, 21-recipient batching/cancellation, outcome consistency, rollback,
competing captures and deterministic unsubscribe-after-read concurrency. The stale
capture rolls back; the next reviewed batch suppresses the withdrawn subscriber.
The SDK statement limit discovered during testing fixes capture batches at ten.

CRM follow-up integration reads the real local CRM API with its JSON filter contract,
verifies the existing Task and matching Contact/Base claim, and links only its UID.
Disabled CRM, wrong-person task and duplicate link are rejected. The owned Task
fixture is inserted through the CRM governed store for SQLite read verification;
existing generic Task creation is PostgreSQL-specific and was not claimed to be
ported by this Marketing release. Fixture records are cleaned by their owner.

All columns have label/description metadata. Two human search phrases per model
return the correct table in the first five actual catalog results. Ruff and strict
MkDocs pass. No foreign table ownership or hidden optional module imports were added.

Reproduce with exact MARKETING_LOCAL_SOURCE_UID (and the other modules' documented
source variables for the full regression):

```bash
.venv/bin/python -m pytest tests/erp/marketing -q
.venv/bin/python -m tests.erp.marketing.run_browser --frontend <frontend-root>
.venv/bin/mkdocs build --strict -f documentation/marketing/mkdocs.yml
```

Use Node 24 and the available Playwright/Chrome runtime for browser execution.
The full tests/erp run needs the established local PostgreSQL binaries and libraries.

## Companion frontend and documentation

Actual browser flow passes subscription evidence/withdrawal/resubscribe, keyboard
Base person and CRM Task choice, explicit audience, queued immutable content, local
capture, simulated reply and existing CRM follow-up navigation. Plain script markup
renders as text. Other module browser transports remain unused until intentional
CRM navigation. Six SDK viewports in light/dark pass; screenshot reviewed. Unsaved
mailing and follow-up selection guards pass. Dropped committed creation response is
reconciled by original-UUID GET with exactly one POST. Stale save/reload passes; its
test waits for the original loaded version before introducing the competing edit.

Held/failed readiness, explicit Retry and both feature Help links pass. Three module
guides join the same General/Modules sidebar and artifact. Frontend evidence records
the full guide/navigation verification. Nine frontend unit files, TypeScript, theme
audit, docs validation, combined Vite/Docusaurus build pass. Existing build-size and
Docusaurus update-check notices are non-failing.

## Remaining gates

No SMTP/provider, external messages, live tracking or real engagement was tested or
implemented. Deferred source capabilities remain in the mapping. Production-engine
concurrency, hosted identities/grants, delegated transports and selective workflow
behavior remain unverified. Only an inactive workflow candidate exists. No platform
migration, push, tag or deployment occurred. Inventory follows after the local cycle.
