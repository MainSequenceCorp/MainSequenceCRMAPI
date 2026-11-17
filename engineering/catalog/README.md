# Catalog — step 3 status

17 November 2026. The bounded Catalog release is implemented and locally verified.
Platform deployment and hosted frontend integration await explicit user approval.
Sales and later modules have not started. Prerequisite Base/CRM adoption was
committed as API `357fef6` and frontend `addaf7d` before Catalog work.

| Stage | Documentation / evidence | State |
| --- | --- | --- |
| Functionality review | [OpenERP coverage](openerp-coverage.md) | Direct source comparison at recorded commit; implemented/adapted/deferred scope explicit. Initial sequencing exception disclosed in ADR. |
| ADR/design | [API ADR](adr/0001-catalog-api.md) | Accepted local scope, ownership, independent migration history, contracts and selected integrations; no new Agent/MCP. |
| Development | [Backend guide](../../docs/catalog/index.md), [concepts](../../docs/catalog/concepts.md), [API](../../docs/catalog/api.md) | Independent records, service/API, strict inputs, rules, audit and companion frontend implemented. |
| Testing | [Verification](verification.md) | 26 final Catalog tests pass; full ERP regression run 477 passed before the final Catalog-only test refinement. |
| Local deployment | [Delivery/recovery](../../docs/catalog/delivery.md) | Actual local SQLite migrations 0001/0002 and API readiness verified on port 38661. |
| Frontend integration | Companion repository `engineering/catalog/README.md` and `docs/catalog/` | Real local API/browser flows, startup/recovery, six viewports/two themes, built user guide and combined artifact pass. |
| Platform release | [Inactive candidate](deployment/catalog-api.yaml.example) | Not validated against the target branch, activated or deployed. Approval and hosted evidence outstanding. |

Products/services, hierarchical categories, reference units, purchase units and
quantity conversion are delivered. Variants, pricing, inventory behavior, supplier
terms and company/translation scope remain explicit later work. No full OpenERP
parity is claimed. User help ships inside the existing ERP site at `/docs/catalog/`.
