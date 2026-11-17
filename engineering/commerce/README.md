# Website and commerce — step 13

- [Pinned OpenERP review](openerp-coverage.md)
- [API ADR](adr/0001-commerce-api.md)
- [Sales complete-plan ADR](../sales/adr/0002-commerce-checkout.md)
- [Concepts](../../docs/commerce/concepts.md), [API](../../docs/commerce/api.md)
- [Local operations](../../docs/commerce/delivery.md)
- [Verification](verification.md)
- [Inert private API workflow](deployment/commerce-api.yaml.example)

Five owned models/revision 0001. Base/Catalog required; Sales/Finance lazy optional.
Merchant screens and separate local customer preview share one ERP static artifact.
No hosted ingress, payment processing or full OpenERP parity claim. Local completion
is recorded with executed evidence; platform deployment remains awaiting approval.
