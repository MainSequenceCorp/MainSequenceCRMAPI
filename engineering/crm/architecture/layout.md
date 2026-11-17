# CRM domain layout

CRM is the currently implemented ERP domain. Existing business behavior and public
URLs are preserved. Future domains can use parallel folders when implemented.

| Material | Owner |
| --- | --- |
| Business source | `src/erp/crm/` |
| Tests and fixtures | `tests/erp/crm/` |
| User or API documentation | `docs/crm/` |
| Maintainer guidance | `engineering/crm/` |
| Instructions and agent definition | `.agents/domains/crm/` |
| Project development skills | `.agents/skills/domains/crm/development/` |
| Domain scripts | `scripts/erp/crm/` |

SDK-managed skill namespaces and repository build/deployment manifests retain
their tool-owned locations. File ownership and original paths are recorded in
[file-moves.json](file-moves.json).

HTTP/MCP adapters live in `api/erp/crm/`. The existing CRM agent implementation
lives in `src/agents/crm/` and `api/agents/crm/`. Its authored prompt and card live
in `.tau/domains/crm/` and `.agents/domains/crm/`; root canonical projections are
checked by `scripts/erp/crm/agent/sync_resources.py`. Runtime business skills
live in `.tau/skills/crm/`.

Existing `api/crm/main.py`, `api/crm/local.py`, `api/tau/main.py` and
`jobs/migrate_crm.py` entrypoints are thin compatibility shims. The workflow keeps
the same API/agent source entrypoints, resource keys, grants and dependencies.
Historical migration resources remain in `src/crm/migrations/`;
`src.crm.migrations:migration` and all revision/table identities remain stable.
Configuration is packaged under `config/erp/crm/settings.yaml`.

Run `.venv/bin/python -m pytest`, `.venv/bin/mkdocs build --strict`,
`.venv/bin/python scripts/erp/crm/agent/sync_resources.py` and
`.venv/bin/python scripts/erp/crm/agent/verify_local_agent.py` from the root.
The actual provider/MCP/history gate remains mandatory before pushing.
