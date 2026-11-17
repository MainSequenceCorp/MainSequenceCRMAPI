# Concepts and integrity rules

A unit group defines compatible quantities. Start with an empty group, then add
its reference unit with factor `1`. Every other active unit requires that reference.
Factor is basis quantity per unit: if Each is the reference, Dozen has factor `12`.
All conversion values are decimal strings. Rounding uses a positive increment,
such as `0.05` or `1`, rather than only a number of decimal places.

A category has an optional parent. The hierarchy must be acyclic and at most 16
levels deep. A category with children, including archived children, cannot move;
rename it or first reorganize its leaf children. Categories with active children
or items cannot be archived. Items require an active category and ancestor chain.

An item has kind `product` or `service`, a default unit and same-group purchase
unit, descriptions and sale/purchase flags. These flags describe availability;
they neither create orders nor grant access. Items own no prices, quantities on
hand, customer/company, taxes, variants or supplier terms in this release.

Unit group/factor/reference/rounding and item kind/default/purchase units cannot
change after creation. Names, codes, descriptions and availability remain editable;
item categories may change. Replacing a quantity definition requires a new record.
UUIDs remain stable and unique codes remain reserved after archive.

Every write requires a capability and, except create, the last observed version.
Reference checks, version fences, the write and audit event share one governed
MetaTables transaction. A conflict leaves both record and audit unchanged. Audit
records identify actor, action, record version, UTC time and changed field names;
they do not retain previous field values or implement undo.

Archive retains records and rejects active dependents. Archive items before units
or categories, non-reference units before the reference, and all units before the
group. Restore in the reverse dependency order. Conversion requires both units
and their group to be active. There is no hard-delete HTTP endpoint.

Storage is owned by `src.erp.catalog` with namespace `erp-catalog`, independent
metadata and migration provider/history/version table. No foreign keys or direct
writes target CRM or Base. Future domains must use published Catalog contracts.
