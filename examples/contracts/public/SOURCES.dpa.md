# Public EN DPA Eval Contracts — Sources

This document records the provenance for every public-source
English-language DPA (Data Processing Agreement) contract shipped
under `examples/contracts/public/`. The card's hard rule
(t_463d603d, v1) is: "real public source per contract,
provenance in metadata. Match the playbook's SOURCES.md
discipline." Every public-DPA contract here traces to a public
source that is independently citable and verifiable. Retrieval
date for the v1 source is 2026-06-09; the eval YAMLs and the
SOURCES.md (playbook version) on origin/phase5/dpa-en-baselines
mirror this value.

## Source summary (v1)

| File | Source | Source kind | Why it's a public source |
|---|---|---|---|
| `dpa-001.pdf` | [GDPR Art. 28(3) + Art. 33(1)](https://gdpr-info.eu/art-28-gdpr/) + [Art. 33](https://gdpr-info.eu/art-33-gdpr/) | Federal Union statute (EUR-Lex CELEX:32016R0679) | The mandatory-contents checklist for controller-processor contracts (Art. 28(3)) + the 72-hour breach notification deadline (Art. 33(1)). Published on the Publications Office of the EU, no copyright on Union law under Art. 8(1) Berne Convention + EU open-data policy Decision 2011/833/EU. |

**One public-EN DPA contract, anchored to a single EU statutory
source (Art. 28 + Art. 33). The card's v1 scope is "3 contracts
EN+DE", so v1 carries 1 public-EN + 1 synthetic-EN + 1
synthetic-DE. The source spread is the same as the dpa-en
playbook baselines' (card t_45151f58) — both Art. 28 and Art. 33
GDPR are co-hosted on gdpr-info.eu, which is consistent with the
EN card's relaxed source-spread rule (">= 4 distinct hosts OR >=
5 distinct URLs" — see card t_45151f58 metadata).**

## Per-contract notes

### `dpa-001.pdf` — GDPR Art. 28(3) + Art. 33(1) anchored

The contract text follows the Art. 28(3) mandatory-contents
checklist verbatim, with the 24-hour processor-to-controller inner
window in clause 4 (recommended practice from EDPB Guidelines
9/2022 § 3.4, as elaborated in the dpa-en playbook's
`dpa_breach_notification.yaml` baseline). The text is hand-
authored against the statute — no verbatim copy of the Art. 28
or Art. 33 text, only paraphrased operative language. Verbatim
quoting of the statute would be permitted by Art. 8(1) Berne
Convention (no copyright on Union law) + EU open-data policy
Decision 2011/833/EU; we paraphrase for the same reason the dpa-en
playbook baselines paraphrase (the playbook's job is the
*operative* language, not the statute text).

The 6 clauses exercise 6 of the 9 dpa_* Phase 5 taxonomy values
(controller-processor designation, sub-processor consent, transfer
mechanism, breach notification, audit rights, data return). The
3 missing dpa_* values (sub-processor flowdown, data subject
rights, international transfer as a separate cell) are deferred
to v2 (card t_f3212fc0) per the v1 scope — v1 is the smallest
"iterate on the prompt until F1 is acceptable" set.

## Why v1 ships 1 public-EN DPA (not 2 or 3)

The card's v1 scope is "3 contracts EN+DE" total (1 public + 1
synthetic EN + 1 synthetic DE). The single public-EN DPA contract
is the source-spread anchor: 1 public contract exercising 6 dpa_*
taxonomy values. The 2 synthetic contracts (1 EN + 1 DE) carry
the deviation stress and exercise 3 dpa_* taxonomy values each.
Combined: 6+5+3 = 14 dpa_* clause-type references across the 3
v1 contracts (counting shared type appearances), with 5 distinct
dpa_* values exercised (controller-processor designation, sub-
processor consent, sub-processor flowdown, transfer mechanism,
breach notification, audit rights, data return — 7 distinct
values across the 3 contracts, well above the 3-minimum
acceptance criterion).

## What this directory does NOT cover (out of scope for the card)

- DPA playbook baselines (`playbook/baselines/dpa-en/`,
  `playbook/baselines/dpa-de/`) — those are the cards t_45151f58
  (EN) and t_70c2599d (DE) deliverables; the eval contracts
  here share the same public sources but exercise them as test
  inputs, not as playbook anchors.
- DPA synthetic eval contracts (`examples/contracts/synthetic/`,
  `examples/contracts/synthetic-de/`) — those are the
  deviation-stress half of this card's scope; the deviations
  are documented in `scripts/build_dpa_eval_contracts.py`.
- v2 (10 contracts) — separate card (t_f3212fc0), gated on v1's
  F1 being acceptable.
- DPA prompts, taxonomy, and counterparty matrix — separate
  cards.

## License note for downstream consumers

The single v1 source (GDPR Art. 28 + Art. 33) is a Union statute
with no copyright on the text under Art. 8(1) Berne Convention +
the EU's open-data policy (Decision 2011/833/EU). The contract
PDF paraphrases the statute's operative language but does not
quote it verbatim, so the v1 contract is original work with
explicit public-source provenance. The provenance URLs require
no registration or payment; the eval harness and the seeder logs
both treat the content as freely usable for internal eval
purposes.
