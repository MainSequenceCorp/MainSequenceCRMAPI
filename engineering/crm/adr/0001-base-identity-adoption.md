# ADR: CRM extraction and adoption of Base

Date: 17 November 2026. Status: implemented and verified locally; hosted release awaiting approval.

The user explicitly authorized expansion step 2 before Base's hosted release.
This changes the local implementation order; it does not authorize a push, tag,
hosted migration or platform deployment. This ADR concerns API extension only.
Agent and MCP design remain deferred.

## Decision

Base owns shared person and organization identity, contact methods and their
labels, postal identity and person–organization relationships. CRM owns sales
ownership, qualification, tags, opportunities, tasks, notes, campaigns, discovery
and source attribution. A CRM contact is a CRM profile of a Base person; a CRM
company is a CRM profile of a Base organization. Neither is a platform login or
an operating company.

Preserve existing CRM UUIDs, history, foreign keys, endpoint names and payload
semantics. Extract each existing identity to the same UUID in Base. Adopting an
existing Directory identity creates a CRM profile only by an explicit command;
Directory access alone never enrolls a person or exposes CRM business records.

During the compatibility period, existing CRM identity columns are a materialized
projection owned by CRM. They support current search, exports and consumers.
They are not an independently editable master. Shared edits use Base-owned
commands and update the CRM projection in the same governed transaction. Base
commands accept registered consumer contributions; Base does not import CRM
models or business services. Application composition installs the CRM consumer.
An adopted record fails closed if its consumer is unavailable. Removing these
compatibility columns is a separate, reviewed migration after consumers migrate.

One selected MetaTables DataSource is required for atomic identity and profile
changes. Base and CRM retain separate metadata, providers, namespaces and Alembic
histories. Base's provider creates only Base tables; CRM's provider creates only
CRM tables. The extraction runner reads CRM and invokes Base's public commands;
it does not migrate another owner's schema or open a database file.

## Lossless conversion and concurrency

Preserve labelled emails and phone numbers, structured names, historical actor
nulls, source timestamps and organization address text. Unknown country codes or
partial employment periods must not acquire invented countries or dates.
Base's public contracts must represent those values before extraction starts.
CRM-only annotations remain in CRM. Preserve all affiliation UUIDs and periods.

Base edits update the affected CRM projection and its existing integer version
atomically. Existing CRM expected-version fences therefore reject stale identity
edits. Each Base change has a Base audit event; CRM commands retain CRM activity.
An error rolls back identity, projection, relationship and audit changes together.

CRM archive affects the CRM profile. It does not silently archive an identity
used elsewhere. Base checks registered consumers before identity archival.
CRM contact merge preserves its existing business-history and redirect behavior;
it must not silently merge identities or rewrite another module's references.
Shared identity merge requires its own explicit policy.

## Controlled cutover

1. Apply additive Base and CRM revisions independently in verified local mode.
2. Produce a bounded extraction inventory, counts and a deterministic digest.
3. Copy records with stable IDs and source-version guards. Refuse ID collisions
   or divergent pre-existing targets; never guess that matching names are equal.
4. Reconcile every shared field and relationship. Repeating a completed batch
   must not duplicate identities or overwrite subsequent edits.
5. Activate adoption only after reconciliation. All mutation entrypoints,
   including import and merge, must participate before activation. An interrupted
   copy remains resumable; CRM cannot use a partially activated directory.

Hosted cutover requires a separately approved release sequence and write pause,
with exact provider revisions, grants, rollback/recovery procedure and consumer
compatibility checked. The old writer must not run after activation.

## Frontend companion and acceptance

Use the existing single ERP site. CRM retains its normal submenu and business
pages; Directory manages shared identity. Show direct navigation between a CRM
profile and its Directory record, and explicit adoption of an existing identity.
Currencies, numbering and other reference configuration remain Administration.
The frontend consumes returned capabilities and contracts; it owns no migrations.

Acceptance requires real local MetaTables upgrade, repeat/collision/recovery
checks, field-by-field reconciliation, bidirectional API edits, stale-version
and rollback tests, archive and merge behavior, import/export compatibility,
existing CRM regression checks and companion frontend verification. Record
unverified paths honestly; local success does not close hosted release gates.
