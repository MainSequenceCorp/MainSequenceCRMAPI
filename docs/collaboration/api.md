# HTTP contracts

Root `/api/collaboration/v1`. Existing SDK request identity is installed once.
Teams map to `collaboration.read`, `.write`, `.manage`, `.configure`; reader/writer/
manager/admin configured through `COLLABORATION_<ROLE>_TEAM_UIDS`. No payload may
supply author identity. Local requests use actual SDK login and reject incoming
identity headers and non-loopback origins.

| Route | Contract |
| --- | --- |
| GET `/ready/` | Module/source/revision, effective capabilities, actor UID and Projects integration availability |
| GET `/discussions/discovery/` | Pinned SDK resource discovery contract |
| GET `/discussions/` | Normalized items/pageInfo; shared-only unless `project_uid` supplied; `search`, `state`, `page_index`, `page_size` |
| POST `/discussions/` | request_uid, name, description, scope, project_uid, audience; 201 detail |
| GET/PUT `/discussions/{uid}/` | Detail or update name/description plus expected_version |
| POST `/discussions/{uid}/actions/{action}/` | expected_version; close/reopen/archive/restore |
| GET/POST `/discussions/{uid}/messages/` | Paged newest-first messages; post request_uid, body, expected_discussion_version; returns discussion/message |
| GET/PUT `/messages/{uid}/` | Message detail; edit body, expected_version, expected_discussion_version |
| POST `/messages/{uid}/retract/` | reason, expected_version, expected_discussion_version; returns discussion/message |
| GET `/messages/{uid}/revisions/` | Author/moderator history with pagination and owner access |
| GET `/discussions/{uid}/audit/` | Manager-only metadata audit with owner access |
| GET `/references/projects/` | Optional authorized public project choices |

Creation example:

```json
{"request_uid":"9ee9f051-7770-4f61-a290-a1e41a24ae28","name":"Delivery planning","description":"Coordinate handoff","scope":"shared","project_uid":null,"audience":"collaboration_readers"}
```

For scope `project`, project_uid is required and audience must be
`authorized_project_readers`. Subject max 200, description 2000, body 8000, reason
1000 characters. Text body/reason must be nonempty after trimming. Unknown fields,
boolean versions and malformed identities yield 422. Versions are positive integers.

Domain errors use `error.code/message`: 403 capability/author/history, 404 missing or
owner-inaccessible linked content, 409 stale/lifecycle/constraint conflict, 503
unavailable storage/integration. Responses never echo inaccessible project titles.
An uncertain POST must be reconciled with GET using the original request UUID;
there is no blanket replay promise. A duplicate UUID conflicts rather than creates
a second discussion/message. Unknown lifecycle actions fail without mutation.
