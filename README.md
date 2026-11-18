# Main Sequence ERP API

One FastAPI deployment serves ERP business modules and Settings. Each module
owns its business contracts, tables and migration history.

- [CRM maintainer guide](engineering/crm/README.md)
- [CRM documentation](docs/crm/index.md)
- [Domain instructions](.agents/domains/crm/AGENTS.md)

- [Shared ERP deployment decision](engineering/architecture/adr/0005-single-erp-api-deployment.md)
- [Local ERP launch and hosted release preparation](engineering/architecture/user-preferences-operations.md)

The shared entrypoint is `api/erp/main.py`. The loopback factory is
`api.erp.local:create_app`. The CRM assistant runs from `api/agents/crm/main.py`.
