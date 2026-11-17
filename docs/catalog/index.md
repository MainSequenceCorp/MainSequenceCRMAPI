# Catalog API documentation

Catalog is the independent owner of product/service definitions, product
categories, unit groups and units. This documentation describes its backend
contracts and local operation. End-user help belongs to the companion ERP
frontend and is shipped at `/docs/catalog/` in the single static artifact.

- [Concepts and integrity rules](concepts.md)
- [HTTP API](api.md)
- [Local delivery and recovery](delivery.md)

Source review, ADR, verification evidence and the inactive workflow candidate are
in `engineering/catalog/` in this repository. Catalog has no CRM/Base business
table prerequisite in this release. It exposes no new Agent or MCP surface.
