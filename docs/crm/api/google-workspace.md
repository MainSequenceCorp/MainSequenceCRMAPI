# Google Workspace API

GoogleConnector owns the Google OAuth registration, personal grants, callback
and source reads. Enable Contacts, Gmail or Calendar in ERP Settings and allow
the user to grant that capability. Access to CRM records follows CRM
permissions. The operator publishes the connector release and supported
CRM workflow keys through the ERP
[connector registry](https://github.com/MainSequenceCorp/MainSequenceERPAPI/blob/main/engineering/architecture/adr/0002-provider-connectors-and-intake-ports.md).

GoogleConnector publishes a manifest and serves connection status, consent,
Calendar discovery and bounded source previews under `/api/connector/v1/`.
CRM previews and writes use the current verified Main Sequence actor.

## Google Contacts Connector intake

Contacts and Gmail correspondents use `POST /api/crm/v1/intake/resolve/` and
`POST /api/crm/v1/intake/commit/` with `crm.google-contacts` or
`crm.google-gmail`. Use the read-purpose claim for resolution and the
write-purpose claim for create or link. A link includes the chosen Contact
UID and version. The response distinguishes archived source links from
possible matches. CRM stores the Contact, audit and source identity in one
governed transaction with the exact connector grant fence.

## Gmail review and owner-selected refresh

The Gmail REST and MCP business commands keep their review and save
contracts. Search reads Gmail headers. Publication revalidates the reviewed
destination, actor, audience and selected message fingerprints before saving.
Use the existing thread selection endpoint to opt in to future replies. It
records a cutoff and preserves the original selection across re-consent.

CRM signs each delegated provider read for the exact actor, release,
installation, operation and arguments. The connector verifies the signature,
Main Sequence workload, current binding generation and grant. Before each eligible sync body
read, the connector checks the CRM enrollment through its private
`POST /api/crm/v1/intake/gmail/selection/` callback. The final governed write
checks the exact active selection and grant generation again. A permitted
owner can stop sync without a usable Gmail grant. Saved history follows CRM
permissions.

For every Google workflow, the connector sends open and close messages to
`POST /api/crm/v1/intake/google/fence/`. This endpoint requires the configured
connector workload. Closure records the exact generation even if an open
never arrived. CRM business writes lock the fence in the same transaction
as the record, audit and provenance.

## Google Calendar Connector intake

Enable `crm.google-calendar` in ERP Settings and connect a Google account.
GoogleConnector supplies the calendar list and authorized, paginated event
previews. Calendar-list permission is optional. With event permission, the
user can enter a calendar ID and choose a range of up to 365 days. Review
previews preserve the organizer, attendees, scheduled time and cancellation
state for the CRM Interaction editor.

| Method | Path | Request and result |
| --- | --- | --- |
| `GET` | `/api/connector/v1/sources/calendar.events/calendars/` | Use the GoogleConnector release with `binding=crm.google-calendar` and an optional `page_token`. Returns calendar IDs and display names and a next page token. |
| `POST` | `/api/connector/v1/sources/calendar.events/preview/` | Send `binding`, `calendar_id`, `time_min`, `time_max` and an optional `page_token` to GoogleConnector. Returns the normalized candidate and distinct resolve and commit claims for each event. |
| `POST` | `/api/crm/v1/intake/calendar/resolve/` | Send `binding` and up to 50 resolve `claim_tokens` to CRM. Resolved items report the source ID, linked Interaction UID and version, its Company, and whether the target is archived. |
| `POST` | `/api/crm/v1/intake/calendar/commit/` | Send `binding`, the commit `claim_token` and `action` of `create`, `link`, `update`, or `skip`. Create and update require reviewed `participants` and accept `subject` and `status`. Create accepts optional Company and Deal references. Update requires the existing `target_uid`, `expected_version` and the original Company context. Link accepts a target Interaction and optional expected version. Skip saves nothing. |

CRM requires read and import access, plus create or edit access for the
corresponding save. It checks the binding, live grant generation and current
module policy. The same governed transaction guards CRM references and stores
the Interaction, source link and audit. An archived target retains the
source link. A duplicate, changed version or closed grant requires a fresh
review.
