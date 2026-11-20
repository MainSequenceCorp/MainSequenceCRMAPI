# Local Base identity adoption

This is expansion step 2, authorized locally by the user. Platform deployment,
triggering pushes/tags, hosted migrations and workflow reconciliation remain
unapproved. The API ADR was written before implementation in the repository's
`engineering/crm/adr/0001-base-identity-adoption.md`.

Base revision `0002` adds lossless identity details, relationship periods,
provenance and consumer claims. CRM revision `0016` adds CRM-owned extraction
links. Each provider owns only its own models, namespace and history. Historical
revisions are unchanged. Base and CRM must use the same selected DataSource for
atomic commands; a mismatch fails closed.

## Controlled local sequence

Use the actual verified local source UUID, not an example or a hosted source.
Keep the local MetaTables service running. Stop both local application APIs on
ports 38641 and 38651 before preparation, copying or activation; the runner
refuses those operations while either port is accepting connections. Do not run
another writer against these local records during cutover.

```bash
.venv/bin/python -m scripts.erp.crm.adopt_base_local prepare --source-uid LOCAL_SOURCE_UUID
.venv/bin/python -m scripts.erp.crm.adopt_base_local inventory --source-uid LOCAL_SOURCE_UUID --inventory /tmp/crm-base-inventory.json
.venv/bin/python -m scripts.erp.crm.adopt_base_local copy --source-uid LOCAL_SOURCE_UUID
.venv/bin/python -m scripts.erp.crm.adopt_base_local reconcile --source-uid LOCAL_SOURCE_UUID
.venv/bin/python -m scripts.erp.crm.adopt_base_local activate --source-uid LOCAL_SOURCE_UUID --inventory /tmp/crm-base-inventory.json
```

The runner verifies real MetaTables local mode, initialized SQLite and the exact
reviewed source before writes. Copy is bounded, commits each record with its
source-version fence, Base audit and extraction link, and resumes using recorded
hashes. A collision or divergence fails without overwriting the target. Original
actor nulls and timestamps are retained in provenance; the new audit identifies
the verified extraction actor. Dates remain at their known precision.

Activation requires field reconciliation and an unchanged inventory. A partial
copy cannot pass the adoption runtime's readiness checks. Restart the shared ERP
API with `CRM_BASE_ADOPTION=1` and the reviewed
`ERP_USER_PREFERENCES_DATA_SOURCE_UID` and
`ERP_USER_PREFERENCES_PROVISIONED_MODULES`. The frontend remains on port 5175.

```bash
CRM_BASE_ADOPTION=1 .venv/bin/uvicorn api.erp.local:create_app --factory --host 127.0.0.1 --port 38641
```

The launcher verifies the pinned local source. CRM readiness verifies the
completed adoption. Startup performs zero migrations or extraction writes.

## Recovery and release

If copying is interrupted, keep writers stopped, inspect the error and repeat
`copy` against the same source. Do not replace IDs or erase conflicting targets.
After activation, do not restart an old CRM writer with adoption disabled.
Downgrades refuse to discard extraction links or adopted Base claims. A rollback
requires an explicit reconciliation/recovery plan, not deletion of the directory.

Run Base and adoption checks against real local MetaTables, CRM regression tests,
strict API documentation checks and the companion frontend build/browser checks.
Existing unrelated CRM extensions still have PostgreSQL-specific query paths;
local identity verification does not claim all extension workflows were ported.
The Google contact creation storage path is integrated; no live Google import or
external OAuth claim follows from local fixtures.

Hosted cutover requires approval of the Base and CRM adoption sequence, write
pause, namespace grants, exact ERP API revision and compatible site artifact.
