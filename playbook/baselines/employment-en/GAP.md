# EN Employment Playbook Baselines — Gap Analysis

This document records the six `employment_*` clause types from
the Phase 5 taxonomy that are NOT covered by a baseline in this
directory, the rationale for the gap, and the planned follow-up.

## The six missing baselines

The Phase 5 clause taxonomy (`docs/15-clause-taxonomy-phase5.md`)
introduces 11 `employment_*` values. This directory ships
baselines for 5 of them:

- `employment_notice_period`
- `employment_remuneration`
- `employment_leave_entitlements`
- `employment_termination_for_cause`
- `employment_non_solicitation`

The following 6 are **not** covered here and require follow-up
work:

| Clause type | Why it is not in this directory | Where it will land |
|---|---|---|
| `employment_probation` | Statutorily anchored in ERA 1996 s.1(3)(d) (statement of particulars must include the probation-period length) and BGB § 622(3) (DE 6-month cap). The UK source is a 5th GOV.UK page ("Written statement of employment particulars" detail on the s.1(3)(d) field). The card chose to ship 5 baselines that pair across 4 × GOV.UK pages + 1 × ABA template rather than overload GOV.UK further; a 5th GOV.UK page would have weakened the source spread. | Follow-up card `t_employment_probation_baseline` (proposed), to ship in the same directory but with a separate GOV.UK page + the BGB § 622(3) anchor for the DE comparison. |
| `employment_garden_leave` | UK-specific concept anchored in ERA 1996 s.20(8). No DE BGB equivalent (DE Freistellung is a related but legally distinct concept). The UK source is a 6th GOV.UK page (the "Garden leave" employer guidance). A single-language UK source is below the card's source-spread bar; the DE complement (Freistellung) belongs to the DE employment baselines card. | Follow-up card `t_employment_garden_leave_baseline` (proposed), to ship as a UK + DE pair across the two employment-EN and employment-DE directories. |
| `employment_non_compete` | DE-anchored (BGB §§ 74 ff. HGB nachvertragliches Wettbewerbsverbot with the Karenzentschädigung compensation rule, max 2 years, written form, clear geographic scope). The US/UK comparator is reasonableness scrutiny under Restatement (Second) Contracts § 188 / UK common-law reasonableness. A single-source EN baseline is below the card's spread bar; the DE BGB anchor is the load-bearing source. | `playbook/baselines/employment-de/` (planned card `t_employment_de_baselines`); the UK/US reasonableness-scrutiny comparator can be a follow-up card. |
| `employment_ip_assignment` | DE-anchored (BGB § 29 ArbNErfG — the Inanspruchnahme claim + separate compensation calculation). UK comparator: UK Patents Act 1977 s.39 + common-law assignment (the "I hereby assign all right, title, and interest" US/UK boilerplate). The DE-anchored card is the load-bearing one; the UK Patents Act 1977 s.39 anchor would be a 7th GOV.UK-adjacent page (legislation.gov.uk, a different host). | `playbook/baselines/employment-de/` (planned card `t_employment_de_baselines`); the UK Patents Act 1977 s.39 anchor can be a follow-up card. |
| `employment_confidentiality_survival` | BGB § 622(6) (Betriebsgeheimnisse nachvertraglich implied regardless of contract) + the in-contract extension (typical 5 years post-term for US/UK commercial practice). No single public source cleanly anchors both the statutory minimum and the typical commercial extension. The ABA Model Employment Agreement has a confidentiality section but not a post-termination survival section as a standalone clause (it is bundled with the in-employment confidentiality). The combination needs 2+ sources, which is below the card's single-source-per-clause bar. | Follow-up card `t_employment_confidentiality_survival_baseline` (proposed), to ship with a combined source (BGB § 622(6) + ABA Model Employment Agreement + UK ERA 1996 implied-term of confidence) once the eval set exercises the deviation. |
| `employment_working_hours` | DE-anchored (ArbZG, max 8h/day, 48h/week average) + UK comparator (Working Time Regulations 1998 SI 1998/1833, max 48h/week, individual opt-out). The UK comparator is the 5th GOV.UK page in this directory's GOV.UK spread; the DE anchor (ArbZG) belongs to the DE baselines card. A 5th GOV.UK page here would weaken the source spread; a 6th page (WTR 1998) would further overload the GOV.UK anchor. | `playbook/baselines/employment-de/` for the DE ArbZG anchor; the UK WTR 1998 anchor can be a follow-up card. |

## Decision log

The "5 baselines or 3 + GAP.md" hedge in the card body exists
because public-source English employment templates are
common, but the *single-source-per-clause* mapping is
constrained by the UK statutory-floor structure: 4 of the
5 baselines here trace to GOV.UK pages anchored to
different sections of ERA 1996, and a 5th GOV.UK page
would have weakened the source-spread without
strengthening the per-baseline provenance.

The decision is therefore: ship 5 baselines now (the
"5 real-public-source" branch of the card's hedge), and
file the remaining 6 as a mix of (a) the
`employment-de`-directory card (which covers
`employment_non_compete`, `employment_ip_assignment`,
`employment_working_hours` from the DE side), and (b) two
follow-up cards (the `employment_probation` /
`employment_garden_leave` UK+DE pair, and the
`employment_confidentiality_survival` combined-source
card) that will land once the eval set exercises the
deviation.

The 11-value coverage will be complete after the
`employment-de` directory and the two follow-up cards
ship. The 5-source spread here (4 × GOV.UK + 1 × ABA
template) plus the 5-source spread of the DE directory
(planned: 4 × DE sources + 1 × UK source) will together
cover the 11 values across at least 8 distinct public
sources.

## What Helena's review card should expect

- 5 baselines in this directory parse cleanly and resolve to
  Phase 5 `employment_*` enum values.
- The SOURCES.md provides 5 distinct, citable public sources
  (4 × GOV.UK pages + 1 × ABA template).
- The 6 missing `employment_*` values are documented in this
  file with a planned follow-up card (or in the DE
  directory card).
- The spotter, when pointed at a real-world employment
  contract, can retrieve and cite at least one of these 5
  baselines (smoke-test will follow once the eval set card
  ships).

## What does NOT count as a "gap" worth filing

- A *longer* notice period than the ERA 1996 s.86 statutory
  minimum (e.g. 6 months for a senior executive) is not a
  gap; it's a stricter-than-baseline position and the matrix
  is supposed to accept it.
- A *shorter* notice period than the s.86 statutory minimum
  is unenforceable and a deviation to flag in the matrix,
  not a gap in the baseline set.
- A counterparty-specific carve-out (e.g. enterprise
  "garden leave" + non-compete combo, SMB without a
  non-compete) is handled by the counterparty matrix, not
  by adding more baselines.
- A *UK-specific* clause that does not exist in the US
  comparator (e.g. UK "garden leave" — the US has no
  equivalent concept) is a follow-up card, not a missing
  baseline in this directory.
