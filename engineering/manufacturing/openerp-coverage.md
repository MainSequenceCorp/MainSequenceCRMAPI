# Manufacturing functionality review

Reviewed before ADR/development, 17 November 2026. Supplied mart-e/openerp reference
commit `b8c8006f649f9f33f271a9dfc1434bb8ffae8798`.

| Reviewed source | Behavior | Selected bounded adaptation |
| --- | --- | --- |
| [mrp_bom.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/mrp/models/mrp_bom.py), _check_bom_lines/explode | Product and component quantities/units, operations, no self-component, recursion prevention, scaled material demand | Independently owned single-level BOM and lines, physical products only, unique components excluding output, exact default-unit quantities, 1–8 components and ordered work steps. No recursive explosion or kits. |
| [mrp_production.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/mrp/models/mrp_production.py), action_confirm/action_assign/_post_inventory/button_mark_done | Confirm/reserve raw materials, work orders, component consumption into production and finished output to stock | Frozen full-batch production snapshot, all-component atomic reservation, sequential work steps, atomic full component consumption plus finished output. Inventory owns movements/balances. |
| [mrp_workorder.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/mrp/models/mrp_workorder.py), button_start/button_finish/_start_nextworkorder | Work sequencing, start/completion, recorded timing and next operation | Manufacturing-owned step status, actor, start/finish evidence and explicit minutes; no capacity calendar or automatic duration/cost claim. |

Financial handoff reuses the verified Inventory → Finance owner contract: signed
fixed-standard-cost movements, balanced valuation/clearing entries and visible net
standard-cost difference. It does not implement OpenERP actual-cost rollup, labor or
overhead allocation. Purchasing continues replenishing stock through its own flow;
Manufacturing does not create duplicate purchase records or imply automatic procurement.

Deferred: multilevel/phantom BOMs, variants, by-products, lot/serial traceability,
partial production/backorders, flexible consumption, scrap, disassembly, work-center
capacity/scheduling, quality/maintenance, labor costing and automatic replenishment.
Local evidence is recorded in [verification](verification.md); hosted gates remain open.
