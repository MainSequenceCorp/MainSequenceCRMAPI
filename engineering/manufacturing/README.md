# Manufacturing — step 12

- [Pinned OpenERP source review](openerp-coverage.md)
- [API ADR](adr/0001-manufacturing-api.md)
- [Concepts](../../docs/manufacturing/concepts.md)
- [API](../../docs/manufacturing/api.md)
- [Local operations](../../docs/manufacturing/delivery.md)
- [Verification](verification.md)
- [Inert workflow candidate](deployment/manufacturing-api.yaml.example)

Five owned models, own revision 0001; Inventory extends its own revision 0002 and
public complete-batch plans. Base/Catalog/Inventory required, Finance optional,
Purchasing independent. Full-batch production with ordered evidence, not complete
OpenERP MRP parity. Companion screens and three guides share the ERP artifact.
Platform deployment and hosted verification remain awaiting approval.
