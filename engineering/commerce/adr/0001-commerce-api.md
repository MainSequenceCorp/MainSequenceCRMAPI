# ADR 0001: Website and commerce API with distinct local public access

Accepted for local implementation, 17 November 2026, after the documented source review.
API extension only; no Agents/MCP. Website and commerce owns Site, Offer, PortalGrant,
Checkout and AuditEvent, separate namespace erp-commerce, metadata, provider/history
and version table. Base/Catalog are prerequisites; Sales checkout and Finance billing
are selected optional owner integrations. Sites/offers can be managed when disabled.

A Site owns a plaintext landing title/body, stable slug, company/currency and draft/
published state. Company/currency/slug are immutable; unpublish before editing content.
Offers belong to one Site and one saleable Catalog service, with exact positive unit
price and captured service/unit description. Draft offers can change and publish;
unpublish before editing, preserving existing checkout snapshots. Only published sites
and offers appear publicly. No arbitrary HTML, JavaScript, URL fetch or execution.

Public acquisition is the local published landing/offer view. Customer self-service
uses a manager-issued portal grant for an existing Base party, one site, 30-minute
expiry, active/revoked status and optimistic version. Store only a SHA-256 digest of
a cryptographically random 256-bit secret. Return the token once; never put it in URLs,
logs, persistent browser storage, audit fields or public collection responses. The
customer enters it into a memory-only portal session and may clear it explicitly.
Grant credentials are not internal platform identities or module permissions.

The local public API is a separate loopback-only app with no internal routes and no
SDK caller-identity header acceptance from customers. Its boundary injects only the
server SDK credential into the standard SDK identity middleware, so owner commands
resolve the verified local merchant; portal tokens never become platform identity. It verifies actual Local SQLite source at setup
and before writes, and uses the existing locally signed-in merchant identity for
owner authorization. Published reads need no token; portal reads/writes require the
scoped token. Enforce host/client/origin loopback, strict bodies, no credential cookies,
no CORS widening, no-store and no-referrer. Deployment of public hosted ingress and
service credentials is deliberately deferred; the inert backend workflow covers the
private API only. Public pages /shop/<slug> use the same ERP static artifact but no
internal rail/bootstrap; all merchant pages remain in the ERP left navigation. The
local customer preview serves that existing built artifact on the public API origin
38762, with no private API proxy. This avoids treating the trusted merchant Vite
development proxy as a customer access boundary. No second frontend build or platform
Static Site resource is introduced.

Checkout accepts original request UUID, site version and 1–20 distinct published
offer IDs/versions with exact quantities in their default unit increments. The server
resolves prices/customer/company/currency; reject caller amounts and owner IDs. Require
current grant/site/offers and active Catalog references. Create a frozen Checkout and
one confirmed Sales order in a guarded atomic same-source transaction, through a
Sales-authored complete plan; include a commerce source link in Sales' existing
related-record map. Deterministic Sales UUID and unique checkout identity prevent
resubmission duplicates. Original-UUID recovery is scoped to the same grant; matching
canonical input hash returns the saved result, a different payload conflicts. Revocation,
unpublication or stale versions roll back the whole checkout. No arbitrary owner writes.

Checkout confirmation is not payment. Merchant managers can create one Finance draft
invoice using its existing complete from-Sales plan, joined to the checkout fence.
Finance owns invoice posting, observed payment recording, allocation and reversal.
The portal projects only its own order reference/net total and linked invoice state,
total, allocated amount and remaining amount; mark paid only for a posted invoice with
full recorded allocation. Label these as recorded payments, not card processing. No
client can claim payment or read another grant/customer's order or internal details.

Private /api/commerce/v1 supports readiness, SDK collections/discovery/detail, Site/Offer
create/update/publish/unpublish, grant issue/revoke, checkout inspection/invoice handoff,
audits and reference pickers. Public local /api/commerce-public/v1 exposes a site by
slug and scoped portal checkout/create/read/list projections. Independent commerce
read/write/manage/configure and owner Sales/Finance grants; no platform identity rebuild.

Required evidence: own fresh/repeated migrations, owner absence, exact price/quantity
validation, strict public projections, token scope/expiry/revocation/no-secret-storage,
replay/races and rollback, optional owner permissions, actual authenticated private
contracts and unauthenticated/token public HTTP checks, invoice/payment reconciliation,
local first deployment, companion merchant/customer browser flows, responsive/theme/
startup/dirty/stale/uncertain behavior and five guides in General → Modules. Finish the
local cycle before Reporting and automation. Hosted deployment requires explicit approval.
