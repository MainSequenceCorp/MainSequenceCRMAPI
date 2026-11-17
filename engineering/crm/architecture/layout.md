# CRM domain layout

CRM is the currently implemented ERP domain. Existing business behavior and public
URLs are preserved. Future domains can use parallel folders when implemented.

| Material | Owner |
| --- | --- |
| Business source | `src/erp/crm/` |
| Tests and fixtures | `tests/erp/crm/` |
| User or API documentation | `docs/crm/` |
| Maintainer guidance | `engineering/crm/` |
| Domain coding instructions | `.agents/domains/crm/` |
| Project development skills | `.agents/skills/domains/crm/development/` |
| Domain scripts | `scripts/erp/crm/` |

SDK-managed skill namespaces and repository build/deployment manifests retain
their tool-owned locations. File ownership and original paths are recorded in
[file-moves.json](file-moves.json).

HTTP/MCP adapters live in `api/erp/crm/`. The existing CRM agent implementation
lives in `src/agents/crm/` and `api/agents/crm/`. Domain coding instructions live
in `.agents/domains/crm/`. The SDK reads the authoritative runtime prompt from
`.tau/SYSTEM.md` and Agent Card from `.agents/agent_card.json`; each has one
authored copy. Runtime business skills live in `.tau/skills/crm/`.

The workflow directly executes `api/erp/crm/main.py`, `api/agents/crm/main.py`
and `jobs/erp/crm/migrate.py`. Local launchers use `api.erp.crm.local:app`.
There are no old-path re-exports, forwarding launchers or resource projection
scripts. Resource keys, grants and workflow dependencies remain unchanged.
The complete migration provider lives in `src/erp/crm/migrations/` and imports
as `src.erp.crm.migrations:migration`. Its persisted catalog identity remains
`src.crm:mainsequence-crm`; all revision and table identities remain unchanged.
Configuration is packaged under `config/erp/crm/settings.yaml`.

Run `.venv/bin/python -m pytest`, `.venv/bin/mkdocs build --strict` and
`.venv/bin/python scripts/erp/crm/agent/verify_local_agent.py` from the root.
The actual provider/MCP/history gate remains mandatory before pushing.
