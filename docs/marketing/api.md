# HTTP API

Root `/api/marketing/v1`. SDK request identity is installed once; payloads cannot
supply actors/mode/result fields. Teams map to `marketing.read/write/manage/configure`
using `MARKETING_<ROLE>_TEAM_UIDS`. Write prepares subscriptions and drafts; manage
queues/captures/cancels/simulates/links. Capture/simulation additionally require
actual MetaTables Local SQLite matching the bound DataSource.

| Route | Contract |
| --- | --- |
| GET `/ready/` | Source/revision, Base readiness, capabilities, capture_available, mode, crm_enabled |
| GET `/{subscribers,mailings}/discovery/` | SDK resource discovery |
| GET `/{subscribers,mailings}/` | Normalized collection; search, state, page_index/page_size |
| POST `/subscribers/` | request_uid, party_uid, email, evidence; creates subscribed |
| POST `/subscribers/{uid}/subscription/` | expected_version, state subscribed/unsubscribed, evidence |
| POST `/mailings/` | request_uid, name, subject, body, sender_email, optional source_label |
| PUT `/mailings/{uid}/` | Same content fields, expected_version; draft only |
| GET `/{subscribers,mailings,recipients}/{uid}/` | Owned detail; recipient includes mailing version, captured payload and events |
| GET/POST `/mailings/{uid}/recipients/` | Paged audience; add request_uid, subscriber_uid, expected_version of mailing |
| POST `/recipients/{uid}/remove/` | expected_version and expected_mailing_version; draft only |
| POST `/mailings/{uid}/queue/` | expected_version and strict boolean acknowledge_local_capture true |
| POST `/mailings/{uid}/capture/` | expected_version; at most ten pending recipients |
| POST `/mailings/{uid}/cancel/` | expected_version; draft/queued only |
| POST `/recipients/{uid}/simulate/` | expected_version, expected_mailing_version, kind opened/clicked/replied/bounced, evidence |
| POST `/recipients/{uid}/followup/` | Both versions and task_uid; link one existing CRM Task |
| GET `/recipients/{uid}/events/` | Paged immutable events |
| GET `/{resource}/{uid}/audit/` | Manager-only paged audit |
| GET `/references/people/`, `/references/people/{uid}/` | Base public active-person reads |
| GET `/references/tasks/?party_uid=...` | Optional CRM Task choices using CRM's JSON filters contract |

Create example:

```json
{"request_uid":"dc4d30fa-36c3-4941-8ddf-c72105d7154c","name":"Local preview","subject":"Delivery update","body":"Plain text","sender_email":"preview@example.com","source_label":"November review"}
```

Names/subject max 200, body 8000, evidence 2000. Positive versions reject booleans.
Unknown fields, invalid email or query bounds fail with 422. Domain envelopes use
error.code/message: 403 permissions/local-only; 404 missing; 409 version/state/
constraint/outcome conflict; 422 reference/eligibility; 503 unavailable prerequisite.
List page size 1–100. Default list has no automatic mutation or provider traffic.

Create/add request UUIDs enable GET reconciliation after uncertain responses; no
blanket replay promise. Reload parent and child after a failed version fence.
Existing foreign task ownership is checked at link time; opening it requires CRM access.
