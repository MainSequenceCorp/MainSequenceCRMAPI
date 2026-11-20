---
name: erp-workflows
description: Discover the ERP modules and tools available to the current person, select the owning module, and use authorized business workflows across modules.
---

# Work across ERP modules

Use `erp_modules_list` through `crm__call_tool` when you need availability
or prerequisites. Use `erp_tools_describe` through the same bridge with the
module key and optional exact tool name. Follow `next_offset` only if you need
more schemas. `crm__list_tools` remains available for the full catalogue.
A visible skill does not guarantee access to its tools.

- For people, organizations, affiliations, and addresses, use [Business
  Directory](skill://base/base-directory/SKILL.md).
- For products, services, categories, units, or conversion, use [Catalog](skill://catalog/catalog-items/SKILL.md).
- For order and delivery work, use [Sales](skill://sales/sales-orders/SKILL.md),
  [Projects](skill://projects/projects-delivery/SKILL.md),
  [Purchasing](skill://purchasing/purchasing-orders/SKILL.md),
  [Inventory](skill://inventory/inventory-stock/SKILL.md), or
  [Manufacturing](skill://manufacturing/manufacturing-production/SKILL.md).
- For invoices, vendor bills and payments, use [Finance
  documents](skill://finance/finance-documents/SKILL.md). For saved bank
  movements, use [Finance reconciliation](skill://finance/finance-bank-reconciliation/SKILL.md).
- For staff records and decisions, use [People](skill://people/people-workforce/SKILL.md).
  Use [Collaboration](skill://collaboration/collaboration-discussions/SKILL.md)
  for internal discussions and [Marketing](skill://marketing/marketing-mailings/SKILL.md)
  for subscribers and draft mailings.
- Use [Commerce](skill://commerce/commerce-merchants/SKILL.md) for merchant
  drafts and checkout records, [report runs](skill://reporting/reporting-runs/SKILL.md)
  for authorized results, and [report schedules](skill://reporting/reporting-schedules/SKILL.md)
  for available scheduled runs.
- Use [personal preferences](skill://settings/settings-preferences/SKILL.md)
  for menu, language and timezone, and [Settings administration](skill://settings/settings-administration/SKILL.md)
  for activation preview and operating configuration.
- For CRM contact records, deals, and outreach work, use the owning [CRM
  skill](skill://crm/crm-core/SKILL.md) and its advertised tools.

Search by the user's terms and ask for a choice if results are ambiguous. Use
the selected record UID for detail. If a tool is unavailable, report its actual
result and continue with any authorized part of the request. Report a write
only after the owner tool confirms it. For a conflict or uncertain write,
read the owner record before retrying. Use the owner's review or confirmation
path for consequential actions.
