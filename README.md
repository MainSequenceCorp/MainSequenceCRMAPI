# Main Sequence CRM API

CRM is the first domain in the ERP repository structure.

- [CRM maintainer guide](engineering/crm/README.md)
- [CRM documentation](docs/crm/index.md)
- [Domain instructions](.agents/domains/crm/AGENTS.md)

The FastAPI entrypoint is `api/erp/crm/main.py`; the CRM agent entrypoint is `api/agents/crm/main.py`.
The migration provider remains `src.crm.migrations:migration`.
