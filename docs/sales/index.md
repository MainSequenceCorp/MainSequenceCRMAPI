# Sales API

Sales owns customer quotations and confirmed commercial orders. It depends on
Base identity/reference reads and Catalog product/unit reads. CRM linkage is
optional. Its independent schema is revision 0001 in namespace `erp-sales`.

- [Concepts and rules](concepts.md)
- [HTTP API](api.md)
- [Local delivery and recovery](delivery.md)

The paired ERP frontend owns end-user help at `/docs/sales/`. This backend site
is technical documentation. Source review, ADR and evidence live in
`engineering/sales/`. Local verification does not authorize platform release.
