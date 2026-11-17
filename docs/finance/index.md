# Finance API

Finance owns an operational invoice/bill and recorded-payment subledger. Base is
its only required business prerequisite. Optional Sales integration consumes its
public read/link-plan contract. This first release uses company currency and fixed
posting roles; no bank transfers or statutory accounting are implied.

- [Concepts](concepts.md)
- [HTTP API](api.md)
- [Local delivery](delivery.md)

Status: independent schema 0001 applied locally; 12 Finance tests pass alongside
13 Sales regressions. Companion frontend and final documentation verification are
in progress. Hosted release remains unapproved.
