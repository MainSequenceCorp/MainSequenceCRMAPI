# ERP MCP phases 0 and 1 verification

Date 19 November 2026. The candidate is local work in the API and ERP site
checkouts. The hosted baseline was read from the existing release.

## Phase 0 baseline

| Snapshot | Runtime or source | Observed catalogue |
| --- | --- | --- |
| Production | Environment `18595d12-f92a-4960-84cd-0c6798a1ad25`, API release `2de75e21-bfe1-4b77-b668-6916488ed317`, active revision `3b3e5a21-1857-45da-ab64-fc039a9028ef` | 104 CRM tools and seven skills with ten files. The 21 Outreach Sequence operations use legacy Campaign tool names. |
| Local source before implementation | API HEAD `3405adcc203793dd582dab8db8ac59233a05c666` with the pre-existing working-tree changes. The existing builder used both CRM feature groups. | 104 CRM definitions. Both catalogues advertise 83 common names with identical input schemas. The remaining 21 names implement the Campaign-to-Outreach Sequence rename in ADR 0004. |
| Local candidate, CRM enabled | Same API HEAD with the pilot working tree, and ERP site HEAD `18055a4d7e04dae144d73332bee66ab50de05963` with its pilot working tree. | All 104 local CRM definitions matched the pre-change snapshot. The new endpoint also advertised the 16 pilot tools and ten grouped skill manifests. |

The raw protocol snapshots are in the API checkout's ignored
`.local/erp/mcp/phase-0-2026-11-19/` directory. They contain tool and skill
metadata without credentials or business record results.

| File | SHA-256 |
| --- | --- |
| `hosted-baseline.json` | `34b0fc9f6f492bf01382ea42a88e589619455e3c9e0264eaaffbba8642afe8f2` |
| `local-crm-before.json` | `6ed889d6dc339f50cfbbf5d8ccf87ff5ac490e1892994d8fdbdadf4012348f14` |
| `local-candidate.json` | `5aa7ac1e674f059b89d2024438f4a9d7e18468ce2b6f6f5c02fecc418c4c8ce4` |
| `tau-bridge-proof.json` | `912441f555ef2a0b6ef3df5e17b0b75151e703ed2be41eaeb0995eb5a16ae89b` |

### Consumer cutover

The API uses the same release key, `/mcp` path, and `crm__list_tools` and
`crm__call_tool` bridge names. Internal CRM skill links and the frontend's
mirrored CRM pack now use the grouped paths. The existing Production revision
continues to serve its legacy names and URIs. Before approving a future
promotion, confirm external consumers refresh discovery or have migrated.

| Existing tool family | Candidate family |
| --- | --- |
| `crm_campaigns_*` | `crm_outreach_sequences_*` |
| `crm_campaign_prompts_*` | `crm_outreach_sequences_prompts_*` |
| `crm_campaign_participants_*` | `crm_outreach_sequences_participants_*` |
| `crm_campaign_tasks_*` | `crm_outreach_sequences_tasks_*` |

The legacy `skill://crm-campaigns/...` resources move to
`skill://crm/crm-outreach-sequences/...`. The `crm-core`, `crm-deals` and all four
`solution-selling` skill paths gain the `crm/` grouping, including their reference
files. The complete old and new manifests are in the raw snapshots. See
[ADR 0004](../adr/0004-crm-outreach-sequences-and-marketing-replies.md).

## Phase 1 local evidence

MetaTables reported local mode, SQLite, a ready and active catalog, and
DataSource `fd16c3b9-0977-5226-b5a8-aff3f47c542b`. The physical file was the
disposable `/tmp/erp-mcp-pilot.sZcbraoG/pilot.sqlite`. The test used SDK sign-in
with the normal loopback API. Fixture creation was limited to this file.
Base revision `0002`, Catalog `0002`, and User Preferences `0003` were applied
there. A second disposable policy scope enabled CRM for compatibility and used
CRM revision `0017` on the same file.

- With CRM inactive and Catalog active, production-path Streamable HTTP
  discovery returned exactly the 16 names in
  [ADR 0006](../adr/0006-erp-mcp.md#4-phase-1-tool-contracts). Each tool's result
  matched the owner REST projection. The conversion returned 24 from two
  dozen. Direct CRM access was denied, as were invalid schemas and missing
  records. The three pilot skill contents matched their local SHA-256 digests.
- With CRM enabled in the second scope, the shared endpoint returned the 104
  unchanged local CRM definitions plus the 16 pilot definitions. The existing
  `crm_settings_get` result matched the REST Settings response.
- A completed local Tau turn loaded the workflow skill, discovered tools through
  `crm__list_tools` and successfully called `base_parties_list` and
  `catalog_items_list` through `crm__call_tool`. The assistant used the existing
  signed-in provider and an isolated local session store.
- Real local Chromium verified Directory and Catalog with CRM inactive, including
  the rail, expanded and direct `/assistant` routes at desktop and phone widths.
  The test also simulated unavailable assistant metadata and checked the shared
  error state. The existing ERP Settings browser regression passed separately.
- The focused backend suite passed 74 tests, including signed caller and
  requester verification, permission revocation between discovery and call,
  unbound workload denial, and Origin admission. Node 24 frontend unit tests,
  TypeScript, theme audit, help navigation and the combined app and docs build
  passed. The strict API MkDocs build passed.

The reproducible opt-in API test is `tests/erp/mcp/test_workflows.py`. It
expects a loopback application in a disposable, verified CRM-disabled scope
with Catalog active. Set `ERP_MCP_TEST_ORIGIN`, `ERP_MCP_TEST_SQLITE`,
`ERP_USER_PREFERENCES_DATA_SOURCE_UID` and the local MetaTables runtime
selection. The paired frontend live browser check is
`tests/application/erp-assistant.browser.mjs`.

Phase 1 has local implementation and verification evidence. Hosted activation,
external client migration, promotion and hosted assistant checks remain future
release work.
