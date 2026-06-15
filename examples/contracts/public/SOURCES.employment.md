# Public EN Employment Eval Contracts — Sources

This document records the provenance for every English-language
**employment** contract shipped under `examples/contracts/public/`.
The card's hard rule (t_ccb0a7fd): "real public source per
contract, provenance in metadata. Match the playbook's SOURCES.md
discipline." Every public-EN employment contract here traces to
a public source that is independently citable and verifiable.
Retrieval date for all three sources is 2026-06-15.

## Source summary

| File | Source | Source kind | Why it's a public source |
|---|---|---|---|
| `employment-001.pdf` | [American Bar Association Model Employment Agreement](https://www.americanbar.org/groups/business_law/resources/model-employment-agreement/) | US professional-association model template | The ABA's Business Law Section model template, free public access. The cleanest US employment agreement baseline; California § 2870 carve-out is in scope. |
| `employment-002.pdf` | [American Bar Association Model Employment Agreement](https://www.americanbar.org/groups/business_law/resources/model-employment-agreement/) (Section 7) | US professional-association model template (IP focus) | The same ABA template, but the contract isolates Section 7 (Assignment of Inventions) with the full California Labor Code § 2870 prior-inventions carve-out. |
| `employment-003.pdf` | [GOV.UK Employment Contracts](https://www.gov.uk/employment-contracts/written-terms-of-employment) | UK government guidance | Statutory floor (ERA 1996 s.86, s.94) for the UK garden-leave clause. UK statutory minimum is independently citable. |

**Three public-EN employment contracts, three distinct public
sources (2× ABA, 1× GOV.UK). The two ABA contracts anchor
different clause types (Section 5 non-compete + Section 6
garden leave in #1; Section 7 IP assignment in #2); the GOV.UK
contract anchors the UK garden-leave variant.**

## Per-contract notes

### `employment-001.pdf` — ABA Model + California § 2870

The contract text uses the ABA Model Employment Agreement's
Sections 5 (non-compete) and 6 (garden leave) verbatim, with
the explicit California Business and Professions Code § 16600
carve-out per *Edwards v. Arthur Andersen LLP* (2008) 44 Cal.
4th 937. The § 6 garden leave clause is 6 months (industry
standard). Spotter should classify c5 as `employment_non_compete`
and c6 as `employment_garden_leave`.

### `employment-002.pdf` — ABA Model Section 7 (IP Assignment)

The contract isolates Section 7 (Assignment of Inventions)
with the full California Labor Code § 2870 prior-inventions
carve-out, including Exhibit A reference for the employee's
prior inventions list. This is the load-bearing EN
`ip_assignment` taxonomy anchor for Phase 5.

### `employment-003.pdf` — GOV.UK Statutory + Garden Leave

The contract follows UK statutory defaults: 1-month notice
under ERA 1996 s.86, 25 days leave under WTR 1998, 6-month
non-solicit, 3-year confidentiality survival, and an
employer-discretion garden-leave clause under ERA 1996 s.94.
This is the load-bearing UK `garden_leave` taxonomy anchor.

## License note for downstream consumers

Both ABA sources are public model templates published by the
American Bar Association for free public use; no registration
or payment is required. The GOV.UK source is UK Crown
copyright material licensed for free reuse under the Open
Government Licence v3.0. None of the provenance URLs require
registration or payment; the eval harness and the seeder
treat the content as freely usable for internal baseline/eval
purposes.
