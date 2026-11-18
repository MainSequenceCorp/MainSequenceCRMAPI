# User Preferences operations

User Preferences owns ERP module activation and private sidebar choices. Base
supplies Business Directory and its Settings destinations in every ERP session.
The [ADR](adr/0001-user-preferences-and-module-activation.md) defines the
dependency model, ownership and access rules.

## Local setup

Start `metatables serve --local` with the installed client and existing SDK
sign-in. Check `metatables --local runtime status` for ready SQLite and the
reviewed local DataSource. Set `erp_source` to that exact UID. Set
`erp_provisioned` to the comma-separated keys with compatible schemas,
including `base`. For a new scope, set `erp_initial_optional` to the reviewed
initial selection. An empty selection keeps only Base active.

```bash
export ERP_USER_PREFERENCES_DATA_SOURCE_UID="$erp_source"
export ERP_USER_PREFERENCES_PROVISIONED_MODULES="$erp_provisioned"
.venv/bin/python -c 'from jobs.erp.crm.migrate import main; main(local=True)'
.venv/bin/python -m scripts.erp.base.setup_local
.venv/bin/python -m scripts.erp.user_preferences.setup_local \
  --source-uid "$erp_source" --provisioned "$erp_provisioned" \
  --active "$erp_initial_optional"
.venv/bin/uvicorn api.erp.local:create_app --factory --host 127.0.0.1 --port 38641
```

The coordinator applies the reviewed module providers and User Preferences.
Prepare any module reference data before activating that module. Policy setup
initializes a new scope once and preserves an existing selection.
For CRM adoption, complete reconciliation and set `CRM_BASE_ADOPTION=1` in the
ERP API process. Set `ERP_USER_PREFERENCES_LOCAL_SCOPE_UID` before setup and
launch only to use a separate local policy scope. The default scope is the
verified local DataSource UID.

Start the frontend with `npm run dev`. Internal ERP API paths proxy to port
38641 by default. Set `ERP_LOCAL_API_ORIGIN` when using a different loopback
port. Existing CRM OAuth routes use this API. Tau uses its own listener.

## Local verification

Revision `0001` was applied and catalog metadata synchronized on ready SQLite,
DataSource `75b7fd29-3b1f-565d-be8d-a3a27d643de2`. Repeat setup preserved
the saved policy. The signed-in loopback API reported 14 ready module bindings.

- The full ERP backend regression passed 518 tests with 58 skipped.
- Focused settings tests exercised private persistence, initial activation,
  dependency checks, stale versions, replay, and rollback of a write whose
  policy version became stale. They used an isolated scope on real local SQLite.
- The signed-in browser verified Base-only navigation, the existing Base Settings
  entries, both new screens, and Manufacturing's dependency preview. Another
  run verified saved hiding, authorized hidden links, a second tab after
  deactivation, and denial at both the Sales API and Finance's Sales handoff.
  The temporary changes were restored.
- The CRM and Business Directory browser test verified adopted identity creation,
  bidirectional edits and conflict handling. Its owned fixture was archived.
- Frontend unit checks, app and guide build, theme audit, and all 84 built guide
  pages passed. The controlled Settings browser matrix used both themes and
  desktop and mobile layouts.

## Hosted release preparation

The shared ERP release runs the `migrate-crm` coordinator before the FastAPI
resource. Configure the approved DataSource and provisioned module list for both
workloads in the exact Environment. The site binds the existing `crm` release
through `VITE_ERP_FASTAPI_RELEASE_UID`. Use the existing release and Team
permissions for business access. The [shared API ADR](adr/0005-single-erp-api-deployment.md)
covers privilege review and rollout approval. Before opening the site, a
verified administrator provisions and checks Base defaults and the required
reference data. The migration Job applies the schema, and Base readiness
requires its singleton settings record.

After migration, an authorized administrator uses the authenticated
`/api/erp/v1/modules/` management route to read version `0`, preflights the
reviewed optional set, then saves that set with `expected_version: 0` and a
request UID. This creates version `1` without restarting business modules.
The site bootstrap becomes ready after initialization and can then open
**Settings → Modules** for subsequent changes.

User Preferences owns the private `erp-user-preferences` namespace. Business
admission needs `data_viewer` on `erp-module-policy` and `data_writer` on the
separate `erp-module-admission` lock namespace. Review the shared workload's
grants separately from verified caller capabilities, including how private
preferences and policy writes are isolated. Prove concurrent writes and
activation ordering on the production engine before exposing activation.
Recover using compatible guarded releases and retain the Base adoption projector.
