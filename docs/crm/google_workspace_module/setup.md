# Configure Google Workspace

GoogleConnector is the credential and callback owner. Follow the connector
repository's operator instructions to apply its MetaTables migrations,
register the approved HTTPS callback, and provision the OAuth registration
in its encrypted table. The provider client ID and secret are stored in the
connector's private namespace.

Enable each required Google API in the OAuth application's Google project.
Use Google Workspace App Access controls for the intended users. Google
applies additional requirements to Gmail read access. Confirm the app
audience and verification status before allowing hosted use.

Bind the exact GoogleConnector release and workload to CRM and ERP Settings.
Configure the CRM operation signing private key and give the connector the
corresponding public key. The request key authenticates CRM's narrowly
scoped provider read authorizations and is independent of the Google OAuth
credentials.

In ERP Settings enable Contacts, Gmail or Calendar independently. A CRM
user can then grant read access for the selected feature. Use one test
account to verify source access, reviewed writes and disconnect against the
intended release after deployment approval. See the
[Google Workspace API](../api/google-workspace.md) for workflow boundaries.
