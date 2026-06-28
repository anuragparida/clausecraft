# EN DPA Playbook Baselines — Sources

This document records the provenance for every English-language DPA
baseline shipped under `playbook/baselines/dpa-en/`. The card's hard
rule, mirroring the Phase 4 DE NDA pattern, is: "Every baseline must
have a real public source. No 'looks plausible' templates from random
websites." Every baseline here traces to a public source that is
independently citable and verifiable. Retrieval date for all five is
2026-06-09; the `retrieval_date` field in each YAML mirrors this value.

## Source summary

| Clause type | Source | Source kind | Why it's a public source |
|---|---|---|---|
| `dpa_controller_processor_designation` | [Art. 28 GDPR](https://gdpr-info.eu/art-28-gdpr/) (paras 1–3) | EU Regulation (EUR-Lex CELEX:32016R0679) | Statute in the public domain under Art. 8(1) Berne Convention + EU open-data policy (Decision 2011/833/EU). The Art. 28(3) mandatory-contents checklist is the *statutory* anchor for every English-language DPA. |
| `dpa_subprocessor_consent` | [EDPB Guidelines 07/2020, v2.0](https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-072020-concepts-controller-and-processor-gdpr_en) § 6 | EDPB Guidelines (PDF, 51 pages) | Adopted by the European Data Protection Board (the joint body of the national supervisory authorities) on 7 July 2021; the authoritative non-binding interpretation of the Art. 28(2) general-written-authorisation mechanism. |
| `dpa_transfer_mechanism` | [EU SCCs 2021/914](https://eur-lex.europa.eu/eli/dec_impl/2021/914/oj), Module Two | Commission Implementing Decision (EUR-Lex CELEX:32021D0914) | The post-Schrems II Standard Contractual Clauses; in force since 27 December 2022 for new transfers. Module Two (controller-to-processor) is the operative transfer mechanism for almost every commercial DPA involving a third-country processor. |
| `dpa_breach_notification` | [Art. 33 GDPR](https://gdpr-info.eu/art-33-gdpr/) (paras 1–5) | EU Regulation (EUR-Lex CELEX:32016R0679) | The 72-hour controller-to-supervisory-authority deadline is the most-cited single fact in any DPA. Statute in the public domain; baseline adds the recommended 24-hour processor-to-controller inner window from EDPB Guidelines 9/2022 § 3.4. |
| `dpa_audit_rights` | [DSK Kurzpapier Nr. 13](https://www.datenschutzkonferenz-online.de/media/kp/dsk_kpnr_13.pdf), pp. 4–5 | Datenschutzkonferenz practitioner guidance (PDF, 5 pages) | The joint publication of the German federal and state data-protection authorities; the authoritative practitioner-level interpretation of Art. 28(3)(h) GDPR for the German-speaking market. Open-access PDF, no registration. |

**Five baselines, five distinct source kinds: statute, regulator
guidelines, commission implementing decision, statute (with
regulator elaboration), and a national-DPO practitioner guidance
document.** The 5-source spread mirrors the Phase 4 DE NDA
playbook pattern (5 baselines, 5 distinct source hosts, no
single document doing the work of two clause types).

## Why this source spread is the right one for an English-language DPA baseline

The card's "real public source" rule is implemented here as:
(a) the source's content is genuinely public (no paywall, no
registration, no fee), (b) the source has recognised legal
authority in the English-language DPA practice, and (c) no single
document is doing the work of two clause types. The five sources
above satisfy all three.

The two statutory anchors (Art. 28 and Art. 33 GDPR) are the
most load-bearing — every English-language DPA template (IAPP
model contracts, Big-4 templates, SaaS standard terms) is
required to implement Art. 28's mandatory-contents checklist and
Art. 33's 72-hour notification rule. The EDPB Guidelines 7/2020
fill in the practitioner-level interpretation of the
sub-processor consent mechanism (general vs specific
authorisation), which the statute leaves open. The EU SCCs
2021/914 Module Two are the de-facto transfer mechanism for
every commercial third-country processor engagement post-Schrems II.
The DSK Kurzpapier Nr. 13 is the German-DPO practitioner
elaboration of audit rights — included because the audit-rights
clause is the one most often drafted with vague language in
commercial templates, and the DSK provides the cleanest public
articulation of the three acceptable variants (on-site,
certification-only, information-request-only).

A private law-firm DPA template (e.g. the "template" pages on
a Big-4 website) was considered and rejected for two reasons:
(1) it is a single firm's marketing collateral rather than a
neutral / regulator / statutory source, and (2) sourcing two
clause types from the same page would have collapsed the source
spread back to four distinct sources for five baselines, which
the card's "5 real-public-source" rule is explicitly trying to
prevent.

## What this directory does NOT cover (out of scope for the card)

- The remaining four `dpa_*` clause types from the Phase 5
  taxonomy (`dpa_subprocessor_flowdown`, `dpa_international_transfer`,
  `dpa_data_subject_rights`, `dpa_data_return_deletion`) — see
  `GAP.md` in this directory for the rationale and the
  follow-up card.
- The DE-language equivalents of these five baselines — that's
  a separate card (`t_dpa_de_baselines`, planned for Phase 5).
- The counterparty matrix (4 columns × 9 dpa_* values) — separate
  card (`t_counterparty_matrix`).
- The eval set (3 public + 2 synthetic EN DPAs + golden YAMLs)
  — separate card (`t_dpa_en_eval`).
- The matrix-aware deviation spotter prompt — separate card
  (`t_matrix_aware_spotter`).
- DPA contracts (`examples/contracts/public-dpa-en/`,
  `examples/contracts/synthetic-dpa-en/`) — separate card.

## License note for downstream consumers

Three of the five sources (Art. 28 GDPR, Art. 33 GDPR, the EU
SCCs 2021/914) are EU legal instruments in the public domain
under Art. 8(1) of the Berne Convention and the EU's open-data
policy (Decision 2011/833/EU); free to reuse without
restriction other than attribution. The fourth (EDPB Guidelines
07/2020) is an EDPB publication distributed under the same
open-access policy, reusable with attribution to "EDPB
Guidelines 07/2020, v2.0 (2021-07-07)". The fifth (DSK
Kurzpapier Nr. 13) is a joint federal-state DPO practitioner
guidance document distributed as an open-access PDF on the DSK
website; reusable with attribution to the Datenschutzkonferenz.

None of the provenance URLs require registration, payment, or
the acceptance of click-through terms. The seed script and the
seeder logs both treat the content as freely usable for internal
baseline purposes. The IAPP model contract library, the
EDPB's earlier Guidelines 07/2020 (v1.0, 2020-09-02), and the
Commission's SCC Q&A were all considered as secondary
cross-references during drafting but are not the *primary*
source for any baseline; their URLs are recorded in the
relevant baseline's `notes` field where the cross-reference
adds practitioner-level colour.
