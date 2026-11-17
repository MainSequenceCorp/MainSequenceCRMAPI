# Marketing functionality review — before ADR

Reference: mart-e/openerp commit `b8c8006f649f9f33f271a9dfc1434bb8ffae8798`
(Odoo 14 lineage), inspected 17 November 2026. Local catalog search for mailing
recipients/consent, delivery traces and subscriber audiences finds CRM stored email,
Contacts and Tasks, but no equivalent mailing execution owner. Existing CRM Campaigns
are live prompted task graphs; this module must not duplicate or migrate them.

| Source | Reviewed behavior | Local bounded adaptation |
| --- | --- | --- |
| [mailing.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/mass_mailing/models/mailing.py) | Mailing wave, subject/body, sender/reply-to, recipient domain/lists, draft/queue/sending/done, remaining recipients exclude prior traces, scheduler, send composer, metrics, unsubscribe tokens and link conversion | Independent Mailing with reviewed explicit audience; immutable queued content, resumable bounded local capture and per-recipient results. No scheduler, SMTP, tracking pixels or public unsubscribe endpoint in this local release. |
| [mailing_contact.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/mass_mailing/models/mailing_contact.py) | Lightweight mailing contact distinct from partner, normalized email, unique list subscription, opt-out and unsubscribe timestamp | Marketing Subscriber references a Base person; no duplicate identity store. Normalized email immutable/unique with explicit subscription evidence and unsubscribe action. A single global subscription scope is conservative; reusable lists and per-list preferences deferred. |
| [mailing_list.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/mass_mailing/models/mailing_list.py) | Eligible count excludes opted-out/blacklisted/invalid addresses; list dedupe/merge; prevent archive of in-use list | Explicit unique mailing recipients, current subscription check before capture, suppressed result retained; list merge and automated segmentation deferred. |
| [mailing_trace.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/mass_mailing/models/mailing_trace.py) | Independent trace grain, scheduled/sent/ignored/error/bounced/opened/replied/clicked dates and state; retain metrics even when mail payload deleted | Recipient capture/result plus immutable DeliveryEvent and audit. Local engagement events are explicitly simulated and never represented as real delivery measurements. |
| [utm.py](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/utm/models/utm.py) | Campaign/source/medium attribution separate from workflow tasks | Mailing source/reference label retained; full UTM URL generation, attribution models and reusable campaign taxonomy deferred to a later Marketing release. |

## Existing owners and limits

Base owns shared persons/contact details. Marketing owns mailing subscription evidence,
audience membership, captured payload and simulated local outcomes. CRM owns follow-up
Tasks and Campaign DAGs, permissions, contact adoption and email provenance. The
optional handoff links an existing readable active CRM Task whose Contact matches
the subscriber's Base CRM consumer claim; no task graph or delivery system is added
to CRM. Task creation occurs through CRM's existing UI/API, not through duplicate
Marketing task storage or foreign-table writes.

Local delivery uses a capture-only channel and exposes its mode in readiness and
all mailing results. It exercises eligibility, batching, outcomes and recovery but
does not establish outbound delivery or provider integration. Hosted SMTP/provider,
unsubscribe ingress, consent-policy/legal review, tracking validation, scheduled
execution, A/B tests, reusable audience lists and public acquisition are future
owning-module releases. No claim of OpenERP parity or external delivery is made.

Status: the bounded adaptations above are implemented and locally verified; the
explicitly deferred capabilities remain outside this release. See the
[executed evidence](verification.md). Existing CRM Task creation uses its legacy
PostgreSQL path; local SQLite integration verifies public reads/linking against an
owned governed Task fixture, not portability of that unrelated write operation.
