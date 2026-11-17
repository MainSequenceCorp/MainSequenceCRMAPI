# Catalog functional reference and coverage

Source inspected 17 November 2026: `mart-e/openerp`, Odoo 14.0, commit
`b8c8006f649f9f33f271a9dfc1434bb8ffae8798`. This is direct source review, not a
running OpenERP acceptance test or a claim of full product parity.

- [Product template](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/product/models/product_template.py): definitions, categories, descriptions, availability, default/purchase units, prices, companies, suppliers, variants and packaging.
- [Categories and variants](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/product/models/product.py): category parent hierarchy and cycle checks, variants and internal references.
- [Units and conversion](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/uom/models/uom_uom.py): compatible groups, single reference unit, ratios, rounding increments, activation and quantity/price conversion.

The first draft preceded this detailed review. The review then informed the
revised ADR and additive 0002 schema before completing business implementation.
Future modules follow the plan's review-before-ADR rule from the beginning.

| Source capability | Decision and current local evidence |
| --- | --- |
| Product/service definitions, internal code, name, general/sales/purchase descriptions, sale/purchase flags and archive | Implemented through owned Item model, API and editor. Real API tests cover products; real browser flow covers a service. Generic product does not imply stocked/consumable behavior; Inventory owns that later distinction. |
| Product category hierarchy and cycle prevention | Implemented with required active item category, cycle/depth/archive guards and frontend parent picker. Adapted to maximum 16 levels and leaf-only moves, explicitly tested. |
| Default and purchase units in the same group | Implemented and tested; omitted purchase unit defaults to default unit. Both become immutable after creation to preserve downstream quantity meaning. |
| Compatible unit groups, ratios and quantity conversion | Implemented and tested with exact rational arithmetic; factor is basis quantity per unit, the inverse of OpenERP's stored factor. Cross-group conversion is rejected. |
| Single reference unit and arbitrary positive rounding increments | Implemented in 0002 with unique active reference, first-reference rule and dependency guards. Empty groups are permitted during separate HTTP setup. Tests cover reference lifecycle and rounding. |
| Conversion rounding defaults | `up` (away from zero) matches the reviewed default; explicit `half_up` and `half_even` alternatives. Tests cover positive/negative quantities, zero, exact results and ties; actual browser verifies 2 dozen → 24.00 units. |
| Mutable unit definitions and history | Deliberate adaptation: group/factor/reference/increment and item kind/units are immutable. Versioned writes and atomic audit protect meaning; changed definitions require new records. |
| Templates, attributes, variants, barcodes and images | Deferred to a later Catalog release. No configurable-product contract is promised to Sales. |
| Supplier product information, packaging, weights and dimensions | Deferred; Catalog owns descriptive fields, while Purchasing terms and Inventory packaging behavior need their own ADR decisions. |
| List price, cost, pricelists and unit price conversion | Deferred. Sales pricing and Finance/Inventory valuation ownership must be decided before implementation; Catalog does not calculate prices or tax. |
| Company scope, currencies and translated descriptions | Deferred to explicit Base integration and a later Catalog contract. No parallel company/currency authority is introduced. |

Implementation: `src/erp/catalog/{metatables,schemas,service,store}`, standalone
`api/erp/catalog`, independent migration revisions 0001/0002, and companion frontend
`src/erp/catalog`. See [verification](verification.md) for executed checks and
[API ADR](adr/0001-catalog-api.md) for boundaries. Sales orders, inventory movements,
financial postings, new Agents and MCP remain outside this step.
