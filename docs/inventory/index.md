# Inventory API and stock ownership

Inventory owns stock policies, locations, balances, movements and immutable stock
entries. Base owns companies/currencies; Catalog owns product/unit definitions.
Sales/Finance are optional integrations. Companion screens/help are in the single
ERP frontend, whose module guides are user-facing rather than these API documents.

- [Concepts and rules](concepts.md)
- [API contracts](api.md)
- [Local deployment and recovery](delivery.md)

Source mapping and API ADR live under engineering/inventory. The bounded implementation and
local backend/browser/full-guide cycle are verified; hosted release is pending approval.
