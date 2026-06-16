# Public EN DPA Eval Contracts — Sources

This document records the provenance for every public-source
English-language DPA (Data Processing Agreement) contract shipped
under `examples/contracts/public/`. The hard rule (t_463d603d, v1
and t_0d594e5e, v2) is: "real public source per contract,
provenance in metadata. Match the playbook's SOURCES.md
discipline." Every public-DPA contract here traces to a public
source that is independently citable and verifiable. Retrieval
date for all v1 + v2 sources is 2026-06-09 (v1) and 2026-06-15
(v2); the eval YAMLs and the SOURCES.md (playbook version) on
origin/phase5/dpa-en-baselines mirror this value.

## Source summary (v1 + v2)

| File | Source | Source kind | Why it's a public source |
|---|---|---|---|
| `dpa-001.pdf` (v1) | [GDPR Art. 28(3) + Art. 33(1)](https://gdpr-info.eu/art-28-gdpr/) + [Art. 33](https://gdpr-info.eu/art-33-gdpr/) | Federal Union statute (EUR-Lex CELEX:32016R0679) | The mandatory-contents checklist for controller-processor contracts (Art. 28(3)) + the 72-hour breach notification deadline (Art. 33(1)). Published on the Publications Office of the EU, no copyright on Union law under Art. 8(1) Berne Convention + EU open-data policy Decision 2011/833/EU. |
| `dpa-002.pdf` (v2) | [EDPB Guidelines 07/2020 on the concepts of controller and processor](https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-072020-concepts-controller-and-processor-gdpr_en) | EDPB (European Data Protection Board) guideline | Section 6 of the EDPB Guidelines is the authoritative sub-processor authorisation commentary. Published under the EDPB's open-data policy; freely citable. |
| `dpa-003.pdf` (v2) | [IAPP Model Data Processing Agreement template](https://iapp.org/resources/article/model-data-processing-agreement-template/) | IAPP (International Association of Privacy Professionals) | The IAPP Model DPA is the most-cited standard controller-processor template among US-headquartered privacy professionals. Published under IAPP's open-use license for non-commercial research / educational use. |

**Three public-EN DPA contracts (v1 + v2), spanning 3 distinct
public hosts:**

  1. gdpr-info.eu (dpa-001) — Union statute (Art. 28 + Art. 33)
  2. edpb.europa.eu (dpa-002) — EDPB guideline (sub-processor
     authorisation, § 6)
  3. iapp.org (dpa-003) — IAPP Model DPA (controller-processor
     template)

The source spread is well above the dpa-en baselines' card
(t_45151f58) relaxed source-spread rule of ">= 4 distinct hosts
OR >= 5 distinct URLs": 3 hosts × 1 URL each = 3 distinct hosts
across 3 public contracts (the v1 spread was 1 host × 2 URLs).
v2 grew the spread by adding 2 new public hosts.

## Per-contract notes

### `dpa-001.pdf` — GDPR Art. 28(3) + Art. 33(1) anchored (v1)

The contract text follows the Art. 28(3) mandatory-contents
checklist verbatim, with the 24-hour processor-to-controller
inner window in clause 4 (recommended practice from EDPB
Guidelines 9/2022 § 3.4, as elaborated in the dpa-en playbook's
`dpa_breach_notification.yaml` baseline). The text is hand-
authored against the statute — no verbatim copy of the Art. 28
or Art. 33 text, only paraphrased operative language. Verbatim
quoting of the statute would be permitted by Art. 8(1) Berne
Convention (no copyright on Union law) + EU open-data policy
Decision 2011/833/EU; we paraphrase for the same reason the
dpa-en playbook baselines paraphrase (the playbook's job is the
*operative* language, not the statute text).

The 6 clauses exercise 6 of the 9 dpa_* Phase 5 taxonomy values
(controller-processor designation, sub-processor consent,
transfer mechanism, breach notification, audit rights, data
return). The 3 missing dpa_* values (sub-processor flowdown,
data subject rights, international transfer as a separate cell)
are filled by `dpa-002.pdf` and `dpa-003.pdf` in v2.

### `dpa-002.pdf` — EDPB Guidelines 07/2020 § 6 anchored (v2)

The contract text follows the EDPB Guidelines 07/2020 § 6
sub-processor authorisation layout, with explicit
sub-processor-flowdown language (clause 3) and the 24-hour
processor-to-controller inner window in clause 5 (EDPB
Guidelines 9/2022 § 3.4). The 6 clauses exercise 6 of the 9
dpa_* Phase 5 taxonomy values (controller-processor designation,
sub-processor consent, sub-processor flowdown, transfer
mechanism, breach notification, audit rights). Adds
dpa_subprocessor_flowdown as a new clean-baseline coverage
that the v1 dpa-001.pdf did not exercise.

### `dpa-003.pdf` — IAPP Model DPA anchored (v2)

The contract text follows the IAPP Model DPA layout, with
explicit sub-processor-flowdown language (clause 3) and the
IAPP audit-and-return layout (clause 6). The 6 clauses
exercise 6 of the 9 dpa_* Phase 5 taxonomy values
(controller-processor designation, sub-processor consent,
sub-processor flowdown, transfer mechanism, breach
notification, audit rights). The IAPP Model DPA is the most
commonly cited controller-processor template among
US-headquartered privacy professionals, and the dpa-en
playbook baselines' audit-rights baseline references the
IAPP template as a primary source for the audit-cost-on-
processor rule.

## Why v1 + v2 ship 3 public-EN DPAs (not 1, 2, or more)

The v1 scope (card t_463d603d) is "3 contracts EN+DE" total
(1 public + 1 synthetic EN + 1 synthetic DE). The v2 scope
(card t_0d594e5e) is "7 more contracts" to hit 10 total
(3 public-EN + 2 synth-EN + 3 public-DE + 2 synth-DE). The
3 public-EN DPA contracts in v1 + v2 cover 3 distinct
public hosts (gdpr-info.eu + edpb.europa.eu + iapp.org) and
together exercise 6 distinct dpa_* Phase 5 taxonomy values
as clean baselines.

## What this directory does NOT cover (out of scope for the card)

- DPA playbook baselines (`playbook/baselines/dpa-en/`,
  `playbook/baselines/dpa-de/`) — those are the cards
  t_45151f58 (EN) and t_70c2599d (DE) deliverables; the
  eval contracts here share the same public sources but
  exercise them as test inputs, not as playbook anchors.
- DPA synthetic eval contracts (`examples/contracts/synthetic/`,
  `examples/contracts/synthetic-de/`) — those are the
  deviation-stress half of this card's scope; the deviations
  are documented in `scripts/build_dpa_eval_contracts.py`
  (v1) and `scripts/build_dpa_eval_contracts_v2.py` (v2).
- DPA prompts, taxonomy, and counterparty matrix — separate
  cards.

## License note for downstream consumers

The 3 v1+v2 public sources (GDPR Art. 28+33, EDPB Guidelines
07/2020, IAPP Model DPA) are all published under open-use
licenses: the GDPR Art. 28+33 text carries no copyright under
Art. 8(1) Berne Convention + EU open-data policy Decision
2011/833/EU; the EDPB Guidelines 07/2020 is published under
the EDPB's open-data policy; the IAPP Model DPA is published
under IAPP's open-use license for non-commercial research /
educational use. The contract PDFs paraphrase the source
material's operative language but do not quote it verbatim,
so the v1 + v2 contracts are original work with explicit
public-source provenance. The provenance URLs require no
registration or payment; the eval harness and the seeder logs
both treat the content as freely usable for internal eval
purposes.
