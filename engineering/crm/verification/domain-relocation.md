# CRM domain relocation verification

Date: 2026-11-17. Existing CRM code, tests, documentation and agent resources
were relocated into domain-owned directories. No new business module, route,
workflow, agent, migration revision or database schema was introduced.

Both working trees were backed up before moving files. Fetched remote changes
were reconciled with existing local work, including localization. API business
source matches the current remote after mechanical import/path rebasing. Frontend
business source retains the pre-existing localization work. SDK dependencies were first restored to the existing lockfile. The user then
explicitly authorized upgrading MetaTables to 0.1.67 after the current hosted
API exposed namespace memberships through `namespaces`. CRM now consumes the
current contract directly; no singular-field fallback was added.

| Check | Local evidence |
| --- | --- |
| File inventory | Every original file has an existing destination; no missing content paths |
| Maintainer/project-skill links | All local Markdown targets resolve in both repositories |
| API suite | 423 passed with MetaTables 0.1.67 using disposable SQLite/PostgreSQL; no skipped tests |
| API documentation | Strict MkDocs build passed; mounted-route documentation tests passed |
| Frontend cases | 32 passed with Node 24; test discovery points to CRM-owned suites |
| Frontend build | TypeScript, Vite and Docusaurus passed; app and `dist/docs/` produced |
| Theme | SDK audit passed for five CSS files |
| Startup browser | Error/deadline/retry and viewport shell checks passed |
| Localization browser | Five languages, fallback, stable drafts/lifecycle and viewport checks passed |
| Guide browser | Help home, 26 links, direct Prompt help and mobile/desktop themes passed |

All eight browser suites passed, including Prompt editing/help, prompter constraints,
campaigns, email workflows and Lead search. Browser runners used the installed
Chrome through a temporary launch adapter. The Prompt fixture serves the built
guide; prompter screenshots use the operating system temporary directory.
Both API and frontend workflow declarations passed branch-specific platform validation.

The actual provider/MCP/restart-history gate and exact-commit hosted deployment
are checked before or during publication.
Their sanitized execution logs are kept in the local task evidence; a local
browser fixture or unit test alone does not establish hosted success.
