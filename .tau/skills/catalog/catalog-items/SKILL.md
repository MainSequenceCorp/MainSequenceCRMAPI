---
name: catalog-items
description: Find ERP products, services, categories and units, and convert quantities using Catalog's current units and rounding rules.
---

# Look up Catalog records

- Use `catalog_items_list` with bounded search and optional `kind`
  (`product` or `service`). Use `catalog_items_get` to confirm the chosen UID.
- Use `catalog_categories_list` and `catalog_categories_get` for categories.
- Use `catalog_unit_groups_list` and `catalog_unit_groups_get` for unit groups.
- Use `catalog_units_list` and `catalog_units_get` for units. Filter the list
  by the exact `group_uid` if known.

Read `pageInfo.hasNextPage` before requesting another `page_index`. Prefer
active records and confirm ambiguous matches.

Use `catalog_units_convert` with a decimal string, the exact source and
target unit UIDs, and the requested rounding mode. Confirm that both active
units belong to the same active group. Report the returned quantity and
whether the service rounded it. If the service reports incompatible or
archived units, ask for the correct units. Conversion calculates a quantity
without writing a record.

Read the [tool reference](references/tools.md) for the complete list.
