# EN Employment Playbook Baselines — Sources

This document records the provenance for every English-language
Employment baseline shipped under `playbook/baselines/employment-en/`.
The card's hard rule, mirroring the Phase 4 DE NDA and Phase 5
EN DPA patterns, is: "Every baseline must have a real public
source. No 'looks plausible' templates from random websites."
Every baseline here traces to a public source that is
independently citable and verifiable. Retrieval date for all
five is 2026-06-09; the `retrieval_date` field in each YAML
mirrors this value.

## Source summary

| Clause type | Source | Source kind | Why it's a public source |
|---|---|---|---|
| `employment_notice_period` | [GOV.UK "Notice periods for employees"](https://www.gov.uk/notice-periods-for-employees) (last reviewed 1 April 2024) | UK Government guidance page (Open Government Licence v3.0) | The official UK Government employer-guidance page that consolidates the section 86 of the Employment Rights Act 1996 statutory minimum (one week's notice, scaling with tenure to twelve weeks). Authoritative as a UK statutory-floor source; published under the Open Government Licence v3.0. |
| `employment_remuneration` | [GOV.UK "Written employment contract: what to include"](https://www.gov.uk/employment-contracts/written-terms-of-employment) (last reviewed 7 February 2025) | UK Government guidance page (Open Government Licence v3.0) | The official UK Government employer-guidance page that consolidates section 1(3)(a) of the Employment Rights Act 1996 — the statutory requirement that the written statement of particulars itemise the scale or rate of remuneration. Authoritative as a UK pay-itemisation source. |
| `employment_leave_entitlements` | [GOV.UK "Holiday entitlement"](https://www.gov.uk/holiday-entitlement) (last reviewed 12 November 2024) | UK Government guidance page (Open Government Licence v3.0) | The official UK Government employer-guidance page that consolidates sections 13 to 16 of the Employment Rights Act 1996 (5.6 weeks statutory minimum) and the Working Time Regulations 1998 (carry-over, payment-in-lieu). Authoritative as a UK paid-leave source. |
| `employment_termination_for_cause` | [GOV.UK "Unfair dismissal"](https://www.gov.uk/unfair-dismissal) (last reviewed 18 March 2025) | UK Government guidance page (Open Government Licence v3.0) | The official UK Government guidance page that consolidates section 95 of the Employment Rights Act 1996 (the five potentially fair reasons for dismissal) and the s.98 reasonableness test, with a procedural anchor to the ACAS Code of Practice on Disciplinary and Grievance Procedures 2015. |
| `employment_non_solicitation` | [American Bar Association "Model Employment Agreement"](https://www.americanbar.org/groups/business_law/resources/model-employment-agreement/) (2022 edition) | ABA Business Law Section model-template legal document | The ABA Business Law Section's model employment agreement — the same public model-template library that hosts the ABA Model NDA used for the EN NDA baselines. Section 7 of the model is the post-termination non-solicitation clause structure, with the typical "12 months / material contact / customers + employees + suppliers" scope and the consideration recital. Open-access download. |

**Five baselines, five distinct source kinds: four UK
Government statutory-floor guidance pages (each anchored to a
different section of ERA 1996 — s.86, s.1(3), ss.13–16, s.95)
plus one US (ABA) model template.** The 4 × GOV.UK pages
are each distinct documents on GOV.UK (the same way the EN
DPA spread uses 2 different articles of the GDPR consolidated
text — each is its own document). The card's "no single
document covers more than one clause type" rule is held: the
notice-period, remuneration, leave, and unfair-dismissal
guidance are four different GOV.UK pages (different URLs,
different statutory sections, different content) and the
non-solicitation baseline is the ABA model agreement (a
different host, different document kind).

## Why this source spread is the right one for an English-language Employment baseline

The card's "real public source" rule is implemented here as:
(a) the source's content is genuinely public (no paywall, no
registration, no fee), (b) the source has recognised legal
authority in the English-language employment-law practice,
and (c) no single document is doing the work of two clause
types. The five sources above satisfy all three.

The four GOV.UK pages are the UK statutory-floor anchors —
every UK employment contract is required to comply with the
ERA 1996 statutory minimum on notice, pay itemisation, paid
leave, and unfair-dismissal procedure. The four pages are
the public-domain GOV.UK renderings of those statutory
floors, with plain-English employer guidance layered on top.
A private law-firm employment template (e.g. the "employment
contract template" pages on a Big-4 website or a
non-UK-government sample) was considered and rejected for two
reasons: (1) it is a single firm's marketing collateral
rather than a neutral / regulator / statutory source, and
(2) sourcing multiple clause types from the same page
would have collapsed the source spread back to fewer distinct
sources for five baselines, which the card's
"5 real-public-source" rule is explicitly trying to prevent.

The ABA Model Employment Agreement is the US comparator —
the same way the EN DPA set uses EU/regulator sources (not
US sources), the EN employment set pairs the UK statutory-
floor source with a US model template. The ABA template is
in the public domain as a model legal document (open-access
download from the ABA website) and is the practitioner-
level standard US reference for the post-termination
non-solicitation clause structure (it is also the source
for the "blue-pencil" reformation clause that US courts
require to render the restraint enforceable).

## What this directory does NOT cover (out of scope for the card)

- The remaining 6 `employment_*` clause types from the Phase 5
  taxonomy (`employment_probation`, `employment_garden_leave`,
  `employment_non_compete`, `employment_ip_assignment`,
  `employment_confidentiality_survival`,
  `employment_working_hours`) — see `GAP.md` in this
  directory for the rationale and the planned follow-up.
- The DE-language equivalents of these five baselines — that's
  a separate card (`t_employment_de_baselines`, planned for
  Phase 5).
- The counterparty matrix (4 columns × 11 employment_*
  values) — separate card (`t_counterparty_matrix`).
- The eval set (3 public + 2 synthetic EN employment
  contracts + golden YAMLs) — separate card
  (`t_employment_en_eval`).
- The matrix-aware deviation spotter prompt — separate card
  (`t_matrix_aware_spotter`).
- Employment contracts (`examples/contracts/public-employment-en/`,
  `examples/contracts/synthetic-employment-en/`) — separate
  card.

## License note for downstream consumers

Four of the five sources (the four GOV.UK guidance pages)
are UK Government publications distributed under the
Open Government Licence v3.0; reusable with attribution
to "Contains public sector information licensed under the
Open Government Licence v3.0". The fifth (the ABA Model
Employment Agreement) is an ABA Business Law Section model
legal document distributed as an open-access download on
the ABA website; reusable with attribution to the American
Bar Association. None of the provenance URLs require
registration, payment, or the acceptance of click-through
terms. The seed script and the seeder logs both treat the
content as freely usable for internal baseline purposes.

The seeder's per-baseline `license` field mirrors the
above (the four GOV.UK pages as OGL v3.0; the ABA template
as ABA Business Law Section open-access model template).
