# SDK and skill refresh — 17 November 2026

Scope: user-requested dependency and skill updates while preparing the ERP
expansion plan. The existing CRM relocation/deployment work belongs to the
other chat. These updates remain local and were not deployed by this task.

| Component | Before | After |
| --- | --- | --- |
| Main Sequence SDK | 9.0.33 | 9.0.40 |
| ms-tau-sdk | 2.0.26 | 3.0.2 |
| MetaTables client | 0.1.67 | 0.1.67, unchanged |

Main Sequence was updated through `code-repository update-sdk`; Tau retains the
existing Git-source dependency convention, now pinned to tag `v3.0.2` and
locked commit `92e31d518a5ce3d4b1a9a62113af53b82cb59966`.
`code-repository sync` refreshed `uv.lock`, the environment and hosted
`requirements.txt`. The update used the existing working Python 3.13
interpreter because the checkout's pyenv selection was not installed; it did
not replace the virtual environment or alter the declared Python version.

The Main Sequence and Tau managed skill bundles were refreshed to their
installed versions. Authenticated platform skills were refreshed in both the
API and frontend checkouts under `.agents/skills/mainsequence_platform/`.
The frontend has no Python runtime dependencies; no Python runtime was added.
Existing SDK-managed namespaces were not hand-edited.

The refreshed Agent and Tau customization guidance explicitly supports multiple
`harness_agent` resources per branch, with `spec.agent_card` and
`spec.runtime_resources`. Only one may use the fallback root Agent Card.
Some general platform prose still contains older singular wording; the explicit
multi-Agent contract is the relevant current guidance. Resource selection
controls loading, not security. This task adds no new Agent or workflow.

| Verification | Result |
| --- | --- |
| Full CRM suite with local PostgreSQL binaries and Docker available | 423 passed, no skipped cases |
| ASGI entrypoint import | FastAPI returned; request identity installed in local mode |
| Tau skill listing/provenance | Six skills, pinned 3.0.2 |
| Main Sequence skill provenance | Pinned 9.0.40 |
| Strict MkDocs build | Passed |
| Actual local Tau / real configured provider | Passed on 3.0.2 using openai-codex/gpt-5.6-luna |
| Actual CRM MCP read, restart history, fresh API read-back | Passed against the owned local MetaTables runtime |
| CRM migration/data identity during agent check | Revision 0015 and 36 bindings retained |
| Hosted deployment of these SDK versions | Not performed |

The first full suite run passed 385 cases and skipped 38 database cases.
Repeating with the available database executables on PATH ran all 423.
Existing FastAPI/Starlette deprecation warnings remain.

Sanitized actual-agent evidence:
`.local/agent-pre-push/6da7f469-4eb8-41f7-bdec-dd42d9cfb012/report.json`.
The checker used private local data and read-only business calls; it did not
create hosted Agents, import mail, change production records or test new
multi-Agent hosted selections.

