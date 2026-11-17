# Collaboration functionality review

Reviewed before ADR/development, 17 November 2026, against `mart-e/openerp` commit
`b8c8006f649f9f33f271a9dfc1434bb8ffae8798` (Odoo 14).

| Source behavior | Bounded decision |
| --- | --- |
| [mail_thread](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/mail/models/mail_thread.py): record-linked messages, author derivation, access hook, field tracking, followers and notifications | Independent internal discussions with verified authors, optional Projects record linkage, explicit audience and owner authorization on every operation. No automatic copy of foreign content. |
| [mail_message](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/mail/models/mail_message.py): subject/body, record model/ID, author, recipients, internal-only flags, record-aware search/read/write rules | Plain-text messages with ordered history, author-only edits, reasoned author/manager retraction and restricted immutable revision history. Linked content requires both Collaboration and record-owner access. HTML, attachments and email provenance are excluded from this release. |
| [mail_channel](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/mail/models/mail_channel.py): channel members, public/private/group scope, invitation checks, moderation and seen state | Shared discussions visible to authorized Collaboration readers; linked project discussions additionally require Projects access. No private channels, member invitation, realtime presence, read receipts or moderation queue in this release. Archive/restore retains history. |
| [mail_followers](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/mail/models/mail_followers.py): record followers/subtypes and recipient data | Subscription, notifications and recipient fan-out deferred to Collaboration; no external delivery or messages are sent. |
| [mail_activity](https://github.com/mart-e/openerp/blob/b8c8006f649f9f33f271a9dfc1434bb8ffae8798/addons/mail/models/mail_activity.py): assigned activities/deadlines/feedback with record rules | Existing CRM follow-up and Projects delivery tasks retain their own ownership. Generic activity orchestration is deferred; no duplicate task engine. |

Existing CRM `docs/crm/concepts/emails.md` and email models/service confirm a reviewed
shared-CRM-reader audience, mailbox-owner OAuth/sync authority and manual/Gmail
provenance. These records are not generic comments. No CRM email extraction, copying,
sharing change or migration is justified by this release. A later explicit migration
would require its own compatibility and audience review.

Local discovery searched record discussions/comments, shared conversation/messages,
and message revisions/read receipts. CRM email and activity tables and Agent session
references have distinct purpose/grain. New Collaboration owns internal discussion
content; existing CRM email remains its source authority. Final verification status
is recorded separately; matching names does not establish full OpenERP parity.
