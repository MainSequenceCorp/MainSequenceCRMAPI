# HTTP API

Root /api/reporting/v1. Installed SDK identity; never trust browser actor/team headers.
Local launcher rejects external origin/host and supplied identity headers. JSON errors
use error.code/error.message; 403 capability/source denial, 404 private/missing record,
409 version/state/lease conflict, 422 strict payload/query validation, 503 unavailable.
Unexpected failures are sanitized. Responses use Cache-Control: no-store.

GET ready/ reports schema_revision, source_uid, local, capabilities, enabled sources,
report kinds and worker_supported. GET {definitions|runs|schedules}/ accepts page_index
(0-based), page_size (1–100), search and state; returns SDK collection-v1 items/pageInfo.
GET {resource}/discovery/ returns SDK discovery-v1. GET {resource}/{uid}/ returns current
private detail; audit/ returns up to 100 recent field-only events. Version is positive
integer (boolean forbidden). Unknown payload fields and query parameters are rejected.

POST definitions/ (201):

```json
{"request_uid":"<original UUID>","name":"Commercial review","kind":"commercial","search":"Acme"}
```

PUT definitions/{uid}/ takes name/kind/search plus expected_version. POST archive/ or
restore/ takes expected_version. GET by original request UID checks uncertain creation.

POST runs/ (201):

```json
{"request_uid":"<original UUID>","definition_uid":"<UUID>","expected_definition_version":1}
```

POST runs/{uid}/advance/, retry/, recover/, cancel/ takes expected_version. Each advance
captures one source; detail shows progress, step_count, steps and recoverable flag, never
lease token or source records. GET result/ returns kind/search/capture window, source
counts and exact totals/status/link summary. GET rows/ and rows/discovery/ expose retained
source rows via the SDK collection contract, searchable/paginated. Row identity is
owner-UUID; source_uid/source/version/path identify the owner record. GET export/ returns
filename/content/mime for a CSV download. POST verify/ takes {} and returns checked,
unchanged, changes and notice; changed/missing rows include source identity. These endpoints
require succeeded state and current access to every source. They never mutate sources.

POST schedules/ (201) takes request_uid/name/definition_uid/interval_minutes; starts paused.
PUT schedules/{uid}/ uses the same editable fields plus expected_version; paused only.
POST activate/ or pause/ takes expected_version. Detail includes next_run_at, last_run_uid,
last_error and definition_name. GET worker/status/ returns supported/available/last_tick_at.
POST worker/tick/ takes {} and exists only on the explicitly local app. The worker controls
no other identity; hosted scheduling requires a separately reviewed authorization design.

Use GET with the original UUID after a timed-out create/queue. Do not create a new request
until the outcome is known. Reload after conflicts or uncertain worker responses. A run
with an expired claim requires explicit recover; failed requires explicit retry.
