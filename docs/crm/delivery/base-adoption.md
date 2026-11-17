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
copy cannot pass the adoption runtime's readiness checks. Restart both APIs with
`CRM_BASE_ADOPTION=1`, explicitly configuring the CRM process with
`configure_local_client()` before launch. The shared ERP frontend remains on
port 5175. The startup switch does not perform migrations or extraction. Reproducible
local launch commands, in separate terminals after activation:

```bash
CRM_BASE_ADOPTION=1 .venv/bin/python -m uvicorn api.erp.base.local:create_app --factory --host 127.0.0.1 --port 38651
.venv/bin/python -m scripts.erp.crm.serve_local_with_base --source-uid LOCAL_SOURCE_UUID
```

The CRM launcher verifies the pinned local source and completed activation
before serving loopback requests. It never prepares or copies data at startup.

Base remains the identity authority. CRM's retained identity columns are an
atomic compatibility projection for its existing queries and consumers. Shared
edits use Base-owned command plans; application composition installs the CRM
projection contributor. The owner writes each table. Missing consumers fail
closed. Removing the old projection columns is a later reviewed change.

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

A hosted release must separately approve the Base and CRM migration/deployment
sequence, write pause, module-specific tags, namespace grants, exact artifact
revisions and the shared ERP build. No hosted cutover occurs in this step.
