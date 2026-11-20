# ERP MCP phase 5 release preflight

**Date** 19 November 2026

**Updated** 20 November 2026

The user approved the phase 5 deployment. Main Sequence rejected the expired
saved session and refresh. The interactive sign-in operation ended cancelled.
A final account check still returned `AUTH_REJECTED` with no Environment
context. The workflow validator, current release revisions and grants,
deployment runs, and hosted assistant could not be checked. Git discovery and
local preparation ran without publishing a ref.

On resuming the rollout on 20 November, branch resolution still returned
HTTP 401 against the expired CLI session. The plugin login ended cancelled.
The official CLI then opened a fresh browser authorization for the
deployment session.

## Published Git baselines

| Artifact | Remote main | Registered source to preserve |
| --- | --- | --- |
| API, migration Job and assistant | `76341c08e112aa1fd4c1072678fa7ece78b3f17a` | `crm` at `api/crm/main.py`, `migrate-crm` at `jobs/migrate_crm.py`, and `crm-assistant` at `api/agents/crm/main.py`. The API and Job paths are registered Production wrappers. The Agent binds `mcp_applications: [{resource: crm}]`. |
| ERP site | `3f4576b6d3c4fdf120f70fe0c449d7a9826b4b5f` | `crm-site`, with the Environment-resolved binding to API resource key `crm`. |

These are Git commits observed on the remotes. The earlier
[Production MCP snapshot](erp-mcp-phase-0-and-1.md) records the previously
observed active API revision. Obtain the current hosted revisions before
selecting a rollback set.

The separate release drafts at `/tmp/erp-mcp-api-phase5.bhjEyQ` and `/tmp/erp-mcp-front-phase5.EewAgu`
are based on the observed remote commits. The API draft carries forward
the published batch catalogue checks. The site draft preserves the
published timeout for module policy and catalogue operations and its strict
committed-navigation build check. The original working trees and deployment
workflows were left in place.

The API draft passed 49 focused catalogue, skill publication, requester
admission, Campaign parity and CRM protocol tests. The ERP site draft passed all ten frontend
tests and the application and documentation builds. The merged drafts still
need the real SDK sign-in and disposable SQLite checks before publishing.

The API draft and local source now accept the 21 cached Campaign tool names and
the seven old CRM skill URLs. Tests read all ten legacy files and check their
manifest digests. The previous Campaign HTTP endpoints now share the Outreach
Sequence handlers and the old bootstrap flag mirrors the current flag.

## Remaining release gates

1. Restore Main Sequence sign-in. Resolve the exact Production branches and
   read the active API, migration Job, assistant and site configuration,
   approved DataSource and modules, and rollback revisions.
2. Reconcile the draft with the Production workflows. Keep the registered
   source paths and resource keys. The currently published API and site use
   `tag_regex: null` and can deploy from a branch push. Validate the planned
   trigger and promotion sequence through the backend before any push.
3. Check the tested Campaign aliases and legacy skill reads on the hosted API
   before promoting the assistant or site. The published API workflow still
   declares legacy Google OAuth callback routes. Verify the existing ingress
   and the connector cutover before promoting a candidate that removes them.
4. Verify the release draft in the approved disposable SQLite runtime. Run the
   Production migration Job, promote the API, verify its direct MCP catalogue
   and requester access, then promote the existing Harness Agent and site.
   In a fresh hosted assistant session, inspect the actual successful
   `erp_tools_describe` and module tool calls. Include Directory, Catalog and
   an active non-CRM module such as Sales. Record the deployment run, revisions,
   the requester used for verification and the rollback set.
