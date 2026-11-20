# Google Workspace module

GoogleConnector owns the Google authorization, credentials and source reads.
Contacts, Gmail and Calendar have independent switches in **Settings →
Connectors**. Each user grants access to the enabled features they choose.
CRM keeps its existing Main Sequence sign-in and record permissions.

| Google source | CRM result |
| --- | --- |
| Saved Google Contacts or Gmail correspondent headers | Review and create or link a [Contact](../concepts/contacts.md). |
| Selected Gmail messages | Review the selected content and publish it to a Contact's shared CRM history. Only the mailbox owner can enroll or stop future replies for one saved thread. |
| Calendar events | Review event participants and create or update an [Interaction](../concepts/interactions.md). Company is optional. |

Previewing creates no CRM records. Review and confirm each business write.
CRM stores stable source identities alongside the governed changes.
Disconnecting closes CRM admission for the Google grant. Saved records stay
available under CRM permissions.

## Module documents

- [Google Workspace API](../api/google-workspace.md) describes review, intake
  and owner-selected refresh.
- [Google Cloud and connector setup](setup.md) describes operator provisioning.
- [User-authorized Google Workspace intake](adrs/0001-google-workspace-intake.md)
  records the original business workflow.
- [Shared CRM email conversations](adrs/0002-selected-email-history.md)
  defines publication, history visibility and owner-selected future replies.
