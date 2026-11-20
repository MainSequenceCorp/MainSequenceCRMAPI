---
name: base-directory
description: Find shared ERP people, organizations, affiliations, and addresses in Business Directory and resolve their exact record identities.
---

# Look up Business Directory records

Use `base_parties_list` to search for people or organizations. Set `kind` to
`person` or `organization` when it helps narrow the result. Confirm the match
before passing its UID to `base_parties_get` or to another module's owner tool.

Use `base_affiliations_list` and `base_affiliations_get` for shared
relationships. Use `base_addresses_list` and `base_addresses_get` for
addresses. Confirm the associated record from the returned UIDs.

Use small pages. Read `pageInfo.hasNextPage` before requesting another
`page_index`. Search active records by default and use `archived` only when
the user needs historical records. Report the name, UID, and relevant details.
If results are ambiguous, ask which record the user means. A shared Directory
person can have a separate CRM Contact UID. Use the UID requested by the
owning tool.

Read the [tool reference](references/tools.md) for the complete list.
