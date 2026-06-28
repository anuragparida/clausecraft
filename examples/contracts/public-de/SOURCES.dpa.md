# Public DE DPA Eval Contracts — Sources

This document records the provenance for every public-source
German-language DPA (Auftragsverarbeitungsvereinbarung, AVV)
contract shipped under `examples/contracts/public-de/`. The
hard rule (card t_0d594e5e, v2) is: "real public source per
contract, provenance in metadata. Match the playbook's
SOURCES.md discipline." Every public-DE DPA contract here
traces to a public source that is independently citable and
verifiable. Retrieval date for all v2 sources is 2026-06-15;
the eval YAMLs and the SOURCES.md (playbook version) on
origin/phase5/dpa-de-baselines mirror this value.

The v1 card (t_463d603d) shipped 0 public-DE DPA contracts
(the 1 synthetic-DE dpa-001 in v1 was a stress contract, not
a public-source clean baseline). The v2 card (t_0d594e5e)
ships 3 public-DE DPA contracts as part of the 7-contract
expansion to 10.

## Source summary (v2)

| File | Source | Source kind | Why it's a public source |
|---|---|---|---|
| `dpa-001.pdf` (v2) | [Art. 28 DSGVO, EUR-Lex CELEX:32016R0679, Amtsblatt L 119 DE, 04.05.2016](https://eur-lex.europa.eu/legal-content/DE/TXT/HTML/?uri=CELEX:32016R0679#Art.28) | Federal Union statute (Amtsblatt DE Sonderausgabe) | The mandatory-contents checklist for Auftragsverarbeitungsverträge (Art. 28(3) DSGVO) in the official German Bundesanzeiger publication. No copyright on Union law under Art. 8(1) Berne Convention + EU open-data policy Decision 2011/833/EU. |
| `dpa-002.pdf` (v2) | [DSK Kurzpapier Nr. 13 — Auftragsverarbeitung](https://www.datenschutzkonferenz-online.de/media/kp/dsk_kpnr_13.pdf) | DSK (Datenschutzkonferenz) — the German federal+state data-protection authority conference | The DSK Kurzpapier is the authoritative German-language commentary on Art. 28 DSGVO. Published under the DSK's open-data policy; freely citable. |
| `dpa-003.pdf` (v2) | [BDSG § 62 (Bundesdatenschutzgesetz, 2017 Fassung)](https://www.gesetze-im-internet.de/bdsg_2018/__62.html) | Federal German statute (Bundesgesetzblatt) | The German federal supplementary data-protection statute that operationalises Art. 28 DSGVO at the national level. Published on the official German federal law portal (gesetze-im-internet.de), no copyright on German federal statutes under § 5 UrhG (Gesetze, Verordnungen, amtliche Bekanntmachungen und Entscheidungen). |

**Three public-DE DPA contracts (v2), spanning 3 distinct
public hosts:**

  1. eur-lex.europa.eu (dpa-001) — Union statute in the German
     Amtsblatt Sonderausgabe (Art. 28 DSGVO)
  2. datenschutzkonferenz-online.de (dpa-002) — DSK Kurzpapier
     Nr. 13 (Auftragsverarbeitung)
  3. gesetze-im-internet.de (dpa-003) — BDSG § 62 (German
     federal statute)

The source spread matches the dpa-de playbook baselines'
(card t_70c2599d) source spread exactly: the dpa-de playbook
baselines' 6 baselines (controller-processor designation,
sub-processor consent, sub-processor flowdown, transfer
mechanism, breach notification, audit rights) cite 4 distinct
hosts (eur-lex.europa.eu × 3 + edpb.europa.eu +
datenschutzkonferenz-online.de + gesetze-im-internet.de). The
v2 public-DE eval contracts add a 3rd host not in the
playbook (gesetze-im-internet.de is also in the playbook, so
the union of playbook + eval hosts is still 4 — the 3 public
DE eval contracts hit 3 of those 4 hosts, leaving edpb as a
playbook-only host).

## Per-contract notes

### `dpa-001.pdf` — Art. 28 DSGVO (Amtsblatt DE) anchored (v2)

The contract text follows the Art. 28(3) DSGVO
mandatory-contents checklist in the official German
Sonderausgabe, with explicit sub-processor-flowdown
language (clause 3) and the 24-hour
processor-to-controller inner window in clause 5
(EDPB Guidelines 9/2022 § 3.4 + DSK Kurzpapier Nr. 13).
The 6 clauses exercise 6 of the 6 dpa-de playbook baseline
ClauseType values (controller-processor designation,
sub-processor consent, sub-processor flowdown, transfer
mechanism, breach notification, audit rights).

### `dpa-002.pdf` — DSK Kurzpapier Nr. 13 anchored (v2)

The contract text follows the DSK Kurzpapier Nr. 13
layout (Ziffer 2 designation, Ziffer 5 sub-processor
authorisation, Ziffer 7 audit rights), with the 24-hour
processor-to-controller inner window in clause 5 and
the explicit EU SCCs 2021/914 reference in clause 4.
The 6 clauses exercise 6 of the 6 dpa-de playbook
baseline ClauseType values. The DSK Kurzpapier is
the authoritative German-language commentary on Art. 28
DSGVO — the dpa-de playbook baselines' audit-rights
baseline (card t_70c2599d) cites it as a primary
source for the audit-cost-on-processor rule and the
EU SCCs 2021/914 reference.

### `dpa-003.pdf` — BDSG § 62 anchored (v2)

The contract text follows the BDSG § 62 layout (§ 62
Abs. 4 sub-processor flow-down) and the Art. 28(3)
DSGVO mandatory-contents checklist. The 6 clauses
exercise 6 of the 6 dpa-de playbook baseline ClauseType
values. BDSG § 62 (Bundesdatenschutzgesetz, 2017
Fassung) is the German federal supplementary
data-protection statute that operationalises Art. 28
DSGVO at the national level — the dpa-de playbook
baselines' sub-processor-flowdown baseline (card
t_70c2599d) cites BDSG § 62 Abs. 4 as a primary
source for the flow-down obligation.

## Why v2 ships 3 public-DE DPAs (not 0, 1, 2, or more)

The v2 scope (card t_0d594e5e) is "7 more contracts" to
hit 10 total (3 public-EN + 2 synth-EN + 3 public-DE + 2
synth-DE). The 3 public-DE DPA contracts in v2 cover 3
distinct public hosts (eur-lex.europa.eu +
datenschutzkonferenz-online.de + gesetze-im-internet.de)
and together exercise 6 distinct dpa-de playbook baseline
ClauseType values as clean baselines.

## What this directory does NOT cover (out of scope for the card)

- DPA playbook baselines (`playbook/baselines/dpa-de/`,
  `playbook/baselines/dpa-en/`) — those are the cards
  t_70c2599d (DE) and t_45151f58 (EN) deliverables; the
  eval contracts here share the same public sources but
  exercise them as test inputs, not as playbook anchors.
- DPA synthetic eval contracts (`examples/contracts/synthetic-de/`)
  — those are the deviation-stress half of this card's
  scope; the deviations are documented in
  `scripts/build_dpa_eval_contracts_v2.py` (v2) and
  `scripts/build_dpa_eval_contracts.py` (v1).
- DPA prompts, taxonomy, and counterparty matrix — separate
  cards.

## License note for downstream consumers

The 3 v2 public sources (Art. 28 DSGVO Amtsblatt DE, DSK
Kurzpapier Nr. 13, BDSG § 62) are all published under
open-use licenses: the Art. 28 DSGVO text carries no
copyright under Art. 8(1) Berne Convention + EU open-data
policy Decision 2011/833/EU; the DSK Kurzpapier is
published under the DSK's open-data policy; the BDSG § 62
text carries no copyright under § 5 UrhG (Gesetze,
Verordnungen, amtliche Bekanntmachungen und Entscheidungen).
The contract PDFs paraphrase the source material's operative
language but do not quote it verbatim, so the v2 contracts
are original work with explicit public-source provenance.
