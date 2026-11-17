# HTTP contracts

Prefix `/api/manufacturing/v1`. Injected SDK identity maps to independent
`manufacturing.read`, `.write`, `.manage`, `.configure` capabilities. No caller-supplied
actor IDs. Inventory and Finance independently authorize their public owner commands.
Readiness checks required owners; disabled Finance does not prevent production.

| Route | Contract |
| --- | --- |
| GET ready/ | ready, local, schema_revision 0001, source, dependencies, capabilities, finance_enabled |
| GET boms/ or orders/ | SDK 0.5.19 collection; page_index/page_size/search/state; unknown queries rejected |
| GET resource/discovery/ | pinned resource-discovery v1; typed columns and status filter |
| GET resource/uid/ | saved record, components or ordered work steps |
| GET resource/uid/audit/ | manager-only recent history, maximum 100 |
| POST boms/ | request_uid, name, item_uid, quantity, components, operations |
| PUT boms/uid/ | same fields without request_uid; expected_version; draft only |
| POST boms/uid/activate/ or archive/ | expected_version |
| POST orders/ | request_uid, name, bom_uid, expected_bom_version, quantity, operating_company_uid, source_uid, destination_uid, production_location_uid |
| POST orders/uid/reserve/, cancel/, complete/, finance/ | expected_version; state and owner fences |
| POST orders/uid/steps/step_uid/start/ | expected_version, expected_step_version |
| POST orders/uid/steps/step_uid/finish/ | same versions, minutes integer, evidence text |
| GET orders/uid/valuation/ | movement_uid, kind, quantity, net_value, currency_code, finance_posted, entries |
| GET references/companies/, items/, locations/, boms/ | public owner collections; boms active only |

Example recipe body (replace UUIDs with readable active physical product identities):

```json
{"request_uid":"11111111-1111-4111-8111-111111111111","name":"BOM-ASSEMBLY-1","item_uid":"22222222-2222-4222-8222-222222222222","quantity":"1","components":[{"item_uid":"33333333-3333-4333-8333-333333333333","quantity":"2"}],"operations":["Assemble","Inspect"]}
```

Amounts/quantities are decimal strings, never binary floats. Positive integer versions
reject booleans; unknown input fields fail. 403 means missing access, 404 absent record,
409 conflict/invalid state/shortage, 422 invalid quantities/references, 503 unavailable
or mismatched owner source. Error envelope `error.code`, `error.message`.

Original creation UUID is the permanent record UID. An uncertain response requires
GET at that UID before resubmission. After uncertain actions reload the order, work
step and linked stock/Finance entries. No implicit retries or global replay promise.
