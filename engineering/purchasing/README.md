# Purchasing — step 11

Local module delivery based on the supplied OpenERP purchase/purchase_stock review.

- [Functionality mapping](openerp-coverage.md)
- [API ADR](adr/0001-purchasing-api.md)
- [Concepts](../../docs/purchasing/concepts.md)
- [HTTP contracts](../../docs/purchasing/api.md)
- [Local deployment/recovery](../../docs/purchasing/delivery.md)
- [Verification](verification.md)
- [Inert deployment candidate](deployment/purchasing-api.yaml.example)

Four owned models and independent migration 0001. Base/Catalog are prerequisites;
Inventory/Finance are optional public owner integrations. Finance adds its own
revision 0002 for source linkage; Inventory supplies complete receipt and fence plans.
Companion Purchase orders screens and two guides join the single ERP site. No new
Agents/MCP and no platform deployment. Full enterprise purchase functionality is not
claimed; partial receipts/backorders/automatic credits remain explicit future work.
