# Local Finance delivery

Verify actual ready local MetaTables SQLite and exact source
`75b7fd29-3b1f-565d-be8d-a3a27d643de2`, then apply only Finance's provider:

```bash
.venv/bin/python -m scripts.erp.finance.setup_local --source-uid 75b7fd29-3b1f-565d-be8d-a3a27d643de2
FINANCE_LOCAL_SOURCE_UID=75b7fd29-3b1f-565d-be8d-a3a27d643de2 .venv/bin/python -m uvicorn api.erp.finance.local:create_app --factory --host 127.0.0.1 --port 38681
```

Revision 0001 creates only Finance's six tables and separate version table.
It was reviewed and formatted before application. No application startup migration
is allowed. The local wrapper verifies runtime/source, loopback origin and SDK
sign-in; hosted deployment must use `api/erp/finance/main.py`, never `local.py`.
Readiness must report local true, revision 0002 and matching Finance/Base sources.
`FINANCE_SALES_ENABLED=false` disables the optional link without removing standalone
Finance. Source conversion also needs already applied Sales/Catalog foundations.

Focused verification requires FINANCE_LOCAL_SOURCE_UID and, for the optional
fixture, SALES_LOCAL_SOURCE_UID, both set to the exact source above:

```bash
.venv/bin/python -m pytest tests/erp/finance tests/erp/sales -q
```

Final full ERP regression: 504 passed, including all 13 Finance scenarios and
13 Sales scenarios. Tests use owned governed local fixtures and remove only
their UUIDs. No production or hosted database is a fallback. Detailed final browser, operational and build evidence is recorded in
`engineering/finance/verification.md`; the paired frontend evidence index records
the combined build and all 50 user guides. Do not infer hosted completeness from local tests.

After an uncertain migration, inspect provider revision/bindings before retrying.
Keep applied history immutable. Preserve the database and use reviewed backup or
forward migration for recovery. Business-write uncertainty requires a fresh GET,
not replay. Disablement preserves tables. Platform deployment requires explicit
user approval after local verification; no push, release tag, active workflow,
hosted migration or reconciliation is currently authorized.

Purchasing integration adds Finance-owned revision 0002: nullable unique purchase
order source on Invoice. Existing revision 0001 is unchanged. Restart local Finance
and its consumers after this additive migration; the verified Purchasing cycle uses
the same Local SQLite source. Hosted application remains separately approval-gated.
