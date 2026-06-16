# EN DPA Playbook Baselines — Gap Analysis

This document records the four `dpa_*` clause types from the
Phase 5 taxonomy that are NOT covered by a baseline in this
directory, the rationale for the gap, and the planned follow-up.

## The four missing baselines

The Phase 5 clause taxonomy (`docs/15-clause-taxonomy-phase5.md`)
introduces 9 `dpa_*` values. This directory ships baselines for
5 of them:

- `dpa_controller_processor_designation`
- `dpa_subprocessor_consent`
- `dpa_transfer_mechanism`
- `dpa_breach_notification`
- `dpa_audit_rights`

The following 4 are **not** covered here and require follow-up
work:

| Clause type | Why it is not in this directory | Where it will land |
|---|---|---|
| `dpa_subprocessor_flowdown` | Closely paired with `dpa_subprocessor_consent` (covered above). The card's "5 baselines" scope chose to ship the *consent gate* (the harder, more variable half) in EN and the *flow-down contract terms* in DE, so the two languages do not duplicate the same source material. The DE Kurzpapier Nr. 13 is a stronger source for the flow-down obligation than for the consent mechanism. | `playbook/baselines/dpa-de/` (planned card `t_dpa_de_baselines`) |
| `dpa_international_transfer` | Operative-transfer-obligation clause. The transfer *mechanism* baseline above (SCCs Module Two) is the meta-clause; the *operative* transfer obligation is the body of Clauses 8.1–8.9 of the SCCs themselves. The body of the SCCs is too long to be a useful deviation spotter target as a single baseline; the spotter currently compares against Module-Two's preamble, and the full operative body is flagged in the matrix as a single "module body" deviation. A separate baseline for this would require summarising Clauses 8.1–8.9 in a way that loses too much structural detail. | Either expand the existing `dpa_transfer_mechanism` baseline to include the operative-body summary as a second `clauses:` entry, or leave as a "covered by the mechanism baseline" residual — see Decision Log below. |
| `dpa_data_subject_rights` | Right-of-access / right-to-erasure / right-to-object mechanism. The clause is structurally simple (the processor must assist the controller in responding to data-subject requests, with a typical SLA of "without undue delay, in any event within 30 days") but the public sources are scattered: Art. 12–22 GDPR + Art. 28(3)(e) GDPR + EDPB Guidelines on the right to erasure (5/2019) + EDPB Guidelines on consent (05/2020). Combining four sources into one baseline is feasible but a single source-and-quote would be cleaner. | Follow-up card `t_dpa_data_subject_rights_baseline` (proposed), to ship in the dpa-de directory so both languages land together. |
| `dpa_data_return_deletion` | End-of-engagement return-or-delete mechanism. Art. 28(3)(g) GDPR is the statutory anchor; the practitioner-level variants (delete only, return only, return-then-delete with certification, return at controller's option) are well documented in EDPB Guidelines 07/2020 and in the DSK Kurzpapier. Same issue as `dpa_data_subject_rights` — multiple sources, would benefit from a single-source design. | Same follow-up card as `dpa_data_subject_rights` (proposed: `t_dpa_post_engagement_baselines`). |

## Decision log

The "5 baselines or 3 + GAP.md" hedge in the card body exists
because public-source English DPAs are scarcer than NDA
templates. After spending 2026-06-09 sourcing, the actual
constraint was *not* a shortage of public sources — it was a
shortage of *clean single-source-per-clause* public
authorities. Art. 28(3) GDPR + Art. 33 GDPR + the EU SCCs
2021/914 + EDPB Guidelines 7/2020 + the DSK Kurzpapier are
five distinct, regulator-grade public sources that pair
cleanly to five baselines. The four remaining `dpa_*` values
each touch more than one source, and forcing a single-source
mapping on them would have collapsed the source spread back
to 5 sources for 9 clause types — which would have
weakened, not strengthened, the per-baseline provenance.

The decision is therefore: ship 5 baselines now (the
"5 real-public-source" branch of the card's hedge), and
file the remaining 4 as a single follow-up card that will
ship a 2-clause pair (`dpa_data_subject_rights` +
`dpa_data_return_deletion`) under a combined source (Art. 28
GDPR + EDPB Guidelines 7/2020 + 5/2019) and a
"covered-by-mechanism" note for the SCC operative body
(`dpa_international_transfer`). The DE baselines directory
will also include `dpa_subprocessor_flowdown`, completing
the 9-value coverage across the two languages.

## What Helena's review card should expect

- 5 baselines in this directory parse cleanly and resolve to
  Phase 5 `dpa_*` enum values.
- The SOURCES.md provides 5 distinct, citable public sources.
- The 4 missing `dpa_*` values are documented in this file with
  a planned follow-up card.
- The spotter, when pointed at a real-world DPA, can retrieve
  and cite at least one of these 5 baselines (smoke-test will
  follow once the eval set card ships).

## What does NOT count as a "gap" worth filing

- A *stricter* drafting choice in a contract clause (e.g. a
  shorter processor-to-controller breach-notification window
  than 24 hours) is not a gap; it's a stricter-than-baseline
  position and the matrix is supposed to accept it.
- A *looser* drafting choice in a contract clause (e.g. "without
  undue delay" rather than a 24-hour window) is a deviation to
  flag in the matrix, not a gap in the baseline set.
- A counterparty-specific carve-out (e.g. healthcare-specific
  data-localisation requirements) is handled by the
  counterparty matrix, not by adding more baselines.
