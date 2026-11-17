# Sales — step 4

17 November 2026. Sales has completed its local implementation, testing, deployment,
frontend integration and documentation cycle. Hosted release remains unapproved.

| Stage | Documentation / evidence | State |
| --- | --- | --- |
| Functional review | [OpenERP source mapping](openerp-coverage.md) | Recorded commit/files inspected before ADR; implemented/adapted/deferred scope explicit. |
| ADR/design | [API ADR](adr/0001-sales-api.md) | Independent ownership, API, permissions and selected integrations; no new Agent/MCP. |
| Development | [Backend guide](../../docs/sales/index.md), [concepts](../../docs/sales/concepts.md), [API](../../docs/sales/api.md) | Quotations/orders, lines, snapshots, exact amounts, lifecycle, audit/version fences and optional CRM read link. |
| Testing | [Verification](verification.md) | 13 focused tests pass; final full ERP regression: 491 passed. |
| Local deployment | [Delivery and recovery](../../docs/sales/delivery.md) | Actual SQLite migration 0001 and SDK-authenticated Sales API on 38671. |
| Frontend integration | Paired frontend `engineering/sales/README.md` and `docs/sales/` | Real local browser lifecycle/recovery, six viewports/two themes, and one built 47-page guide with General/Modules navigation pass. |
| Hosted release | [Inactive planning example](deployment/sales-api.yaml.example) | Not validated, activated or deployed; explicit approval and hosted evidence required. |

This bounded release does not promise full OpenERP parity. It records net
commercial terms, not tax invoices, payments or deliveries. Each future owning
module must use the public Sales contract and preserve module independence.
