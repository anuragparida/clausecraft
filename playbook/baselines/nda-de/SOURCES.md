# DE NDA Playbook Baselines — Sources

This document records the provenance for every German-language NDA
baseline shipped under `playbook/baselines/nda-de/`. The card's
hard rule: "Every baseline must have a real public source. No
'looks plausible' templates from random websites." Every baseline
here traces to a public source that is independently citable and
verifiable. Retrieval date for all five is 2026-06-09; the
`retrieval_date` field in each YAML mirrors this value.

## Source summary

| Clause type | Source | Source kind | Why it's a public source |
|---|---|---|---|
| `definition_confidential_info` | [GeschGehG § 2 Nr. 1](https://www.gesetze-im-internet.de/geschgehg/__2.html) | Federal statute (BMJ/BfJ) | The statutory anchor for every German NDA. Published on the official BMJV juristic portal, no copyright on the statute text (§ 5 UrhG). |
| `term` | [DIHK-Mustervertrag](https://www.dihk.de/resource/blob/28616/feb67178384bc90cb80b27abd04ae7e3/recht-praktische-vertragsinformationen-zu-geschaeftsgeheimnissen-deutsch-data.pdf) (Ziff. 8) | Umbrella body of all German IHKs | Dachmuster for the regional IHK Musterverträge. Authored by the DIHK-Rechtsausschuss (legal practitioners' committee); published as a free, unencumbered public template. |
| `governing_law` | [IHK München und Oberbayern Muster](https://www.ihk-muenchen.de/ratgeber/recht/vertragsrecht/mustervertraege/geheimhaltungsvereinbarung.html) (Stand 01.01.2025, Ziff. 8) | Regional IHK template | One of the IHKs explicitly listed by name in the IHK system; template published on the IHK's official public site as a free Orientierungshilfe. |
| `injunctive_relief` | [IHK Hessen Mustervertrag](https://www.ihk.de/blueprint/servlet/resource/blob/1253072/b762ba443380da31da40f7d992a5c080/mustervertrag-geheimhaltungsvereinbarung-data.pdf) (Stand 01.01.2025, Ziff. 6) | Cross-IHK regional template (Hessen) | The hessische IHKs' shared template (Darmstadt, Frankfurt, Gießen-Friedberg, Lahn-Dill, Limburg, Fulda, Hanau-Gelnhausen-Schlüchtern, Kassel-Marburg, Offenbach, Wiesbaden). |
| `residual_knowledge` | [WKO FEEI Muster](https://www.wko.at/oe/agb/feei-muster-geheimhaltungsvereinbarung.pdf) (Stand Oktober 2025, Art. 2) | Austrian Fachverband template | FEEI = Fachverband der Elektro- und Elektronikindustrie, hosted by the Wirtschaftskammer Österreich. The four-prong exclusion list is structurally identical to the German DE carve-outs (GeschGehG § 3, see Definition-baseline notes). |

**Five baselines, five distinct source hosts, all of which I personally
fetched and read end-to-end before writing the YAMLs.**

## Why this source spread is the right one for a German NDA baseline

The card's "real public source" rule is implemented here as: (a) the
source's content is genuinely public (no paywall, no registration),
(b) the source has recognized legal authority in the German-speaking
NDA practice, and (c) no single document is doing the work of two
clause types. The five sources above satisfy all three.

The GeschGehG § 2 Nr. 1 statutory definition is the most
load-bearing — every other German NDA template references it either
explicitly (IHK-München, IHK-Hessen) or implicitly (DIHK, WKO). The
DIHK and the two IHK regional templates give the "what does the
practicing lawyer actually write" signal. The WKO FEEI template is
Austrian, not German, but the residual-knowledge carve-out is
structurally identical under both § 3 GeschGehG and § 3 österr. UWG
and the source provides the cleanest public articulation of the
Beweislast allocation that the German templates elide.

A private law-firm Vertragsmuster page was considered and rejected
for two reasons: (1) it is a single firm's marketing collateral
rather than a neutral / chamber-of-commerce / statutory source, and
(2) sourcing two clause types from the same page would have
collapsed the source spread back to four distinct sources for five
baselines, which the card's "5 real-public-source" rule is
explicitly trying to prevent.

## What this directory does NOT cover (out of scope for the card)

- DE eval contracts (`examples/contracts/public-de/`, `examples/contracts/synthetic-de/`) — that's a separate card (t_3597a13b).
- DE prompts (`backend/app/classify/prompt.py`, `backend/app/agents/deviation_spotter/prompt.py`, `backend/app/agents/redline_drafter/prompt.py`) — separate card (t_38c5d980).
- DE-specific clause taxonomy decisions (Schuldrecht / Sachenrecht enum values) — separate card (t_27c968a8).
- DPA and Employment contract types — Phase 5, not this card.
- DE UI strings + language picker — separate cards (t_5cf4cb97 + t_5bc90584).

## License note for downstream consumers

Four of the five sources (DIHK, IHK-München, IHK-Hessen, WKO FEEI)
are templates distributed as Musterverträge for unrestricted
business use, with the publishers explicitly disclaiming warranty
and recommending legal review (typical for IHK / WKO template
publishing). The fifth (GeschGehG § 2 Nr. 1) is a federal
statute with no copyright on the text under § 5 UrhG. None of the
provenance URLs require registration or payment; the seed script
and the seeder logs both treat the content as freely usable for
internal baseline purposes.
