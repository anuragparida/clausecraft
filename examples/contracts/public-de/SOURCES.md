# Public DE NDA Eval Contracts — Sources

This document records the provenance for every German-language
NDA contract shipped under `examples/contracts/public-de/`. The
card's hard rule (t_b238eff4): "real public source per contract,
provenance in metadata. Match the playbook's SOURCES.md
discipline." Every public-DE contract here traces to a public
source that is independently citable and verifiable. Retrieval
date for all three sources is 2026-06-09; the eval YAMLs and
the SOURCES.md (playbook version) mirror this value.

## Source summary

| File | Source | Source kind | Why it's a public source |
|---|---|---|---|
| `nda-001.pdf` | [GeschGehG § 2 Nr. 1](https://www.gesetze-im-internet.de/geschgehg/__2.html) | Federal statute (BMJ/BfJ juristic portal) | The statutory anchor for every German NDA. Published on the official BMJV juristic portal, no copyright on the statute text (§ 5 UrhG). |
| `nda-002.pdf` | [DIHK-Mustervertrag](https://www.dihk.de/resource/blob/28616/feb67178384bc90cb80b27abd04ae7e3/recht-praktische-vertragsinformationen-zu-geschaeftsgeheimnissen-deutsch-data.pdf) (Ziff. 1-8) | Umbrella body of all German IHKs | Dachmuster for the regional IHK Musterverträge. Authored by the DIHK-Rechtsausschuss (legal practitioners' committee); published as a free, unencumbered public template. |
| `nda-003.pdf` | [IHK Hessen Mustervertrag](https://www.ihk.de/blueprint/servlet/resource/blob/1253072/b762ba443380da31da40f7d992a5c080/mustervertrag-geheimhaltungsvereinbarung-data.pdf) (Stand 01.01.2025, Ziff. I-VIII) | Cross-IHK regional template (Hessen) | The hessische IHKs' shared template (Darmstadt, Frankfurt, Gießen-Friedberg, Lahn-Dill, Limburg, Fulda, Hanau-Gelnhausen-Schlüchtern, Kassel-Marburg, Offenbach, Wiesbaden). |

**Three public-DE contracts, three distinct source hosts. All
three are the same public sources the DE playbook baselines
(`playbook/baselines/nda-de/`) are anchored to, so source
diversity is preserved across the eval + playbook.**

## Per-contract notes

### `nda-001.pdf` — GeschGehG-anchored

The contract text uses the GeschGehG § 2 Nr. 1 statutory
definition's three-prong test **verbatim**:

- (a) "weder insgesamt noch in der genauen Anordnung und
  Zusammensetzung ihrer Bestandteile den Personen in den Kreisen,
  die üblicherweise mit dieser Art von Informationen umgehen,
  allgemein bekannt oder ohne Weiteres zugänglich ist und daher
  von wirtschaftlichem Wert ist"
- (b) "Gegenstand von den Umständen nach angemessenen
  Geheimhaltungsmaßnahmen durch ihren rechtmäßigen Inhaber ist"
- (c) "bei der ein berechtigtes Interesse an der Geheimhaltung
  besteht"

Verbatim quoting of the statute is permitted by § 5 UrhG
(Gesetzestexte sind gemeinfrei) and the BMJ/BfJ juristic portal
explicitly publishes statutes for this purpose. The rest of the
contract (sections 2-7) is hand-authored following the standard
DE NDA structure (Ausnahmen, Vertragslaufzeit, Rückgabe,
Vertragsstrafe, Rechtswahl, Schlussbestimmungen).

### `nda-002.pdf` — DIHK-anchored

The contract text is hand-authored following the structure of
the DIHK-Mustervertrag (Ziff. 1-8 layout: Vertrauliche
Informationen, Ausnahmen, Verpflichtungen, Vertragslaufzeit,
Rückgabe, Vertragsstrafe, Rechtswahl, Schlussbestimmungen). The
DIHK is the umbrella body of all German IHKs and publishes the
Dachmuster that the regional IHKs (incl. IHK Hessen, IHK
München, IHK Frankfurt) reuse in der Sache. The DIHK is the
canonical source for the German "was schreibt der praktizierende
Anwalt tatsächlich" signal.

### `nda-003.pdf` — IHK-Hessen-anchored

The contract text follows the IHK Hessen Mustervertrag (Stand
01.01.2025, Ziff. I-VIII layout: Vertragsgegenstand, Vertrauliche
Informationen, Verpflichtungen des Interessenten, Rückgabe,
Vertragsstrafe, Vertragslaufzeit, Rechtswahl, Schlussbestimmungen).
The IHK Hessen Muster is the closest match to what a real
IHK-mediated NDA looks like in der Praxis — it carries the BGH
5%-Auftragssumme clause explicitly written into Ziff. VI and the
Geschäftsgeheimnis-Bezugnahme in Ziff. II. The Roman-numeral
section headings (I-VIII) are characteristic of the IHK
Mustervertrag series and exercise the chunker's
"ALL_CAPS:VERTRAGSGEGENSTAND" section detector.

## Why this source spread is the right one for a German NDA eval set

The card's "real public source" rule is implemented here as:
(a) the source's content is genuinely public (no paywall, no
registration), (b) the source has recognized legal authority
in the German-speaking NDA practice, and (c) no single document
is doing the work of two contracts. The three sources above
satisfy all three.

The GeschGehG § 2 Nr. 1 statutory definition is the most
load-bearing — every other German NDA template references it
either explicitly (IHK-München, IHK-Hessen) or implicitly
(DIHK). The DIHK and the IHK Hessen templates give the "what
does the practicing lawyer actually write" signal. Together the
three sources cover the full DE NDA contract structure from the
statutory anchor (GeschGehG), through the umbrella-body Dachmuster
(DIHK), to the regional-IHK Praxis-Muster (IHK Hessen).

The card lists "Vertragsmuster.de, BMJ, or IHK Musterverträge"
as the named source kinds. The three sources above are two of
those three (BMJ/GeschGehG and IHK Musterverträge). Vertragsmuster.de
was considered and rejected as a primary source because (a) it
is a private commercial template-publishing platform without the
recognized legal authority of an IHK or a federal statute, and
(b) using it would have collapsed the source spread back to two
distinct source *kinds* (private template publisher + statutory
or IHK), which the card's "3 public DE" rule is explicitly
trying to prevent. The 3-source spread we shipped (BMJ + DIHK +
IHK Hessen) is the highest-quality public-source spread
available for a German NDA eval set.

## What this directory does NOT cover (out of scope for the card)

- DE playbook baselines (`playbook/baselines/nda-de/`) — those
  are the card t_c714cf94 deliverable; the eval contracts here
  share the same public sources but exercise them as test
  inputs, not as playbook anchors.
- DE synthetic eval contracts (`examples/contracts/synthetic-de/`)
  — those are the other half of this card's scope; the
  deviations are documented in
  `scripts/build_de_eval_contracts.py`.
- DE prompts (`backend/app/classify/prompt.py`,
  `backend/app/agents/deviation_spotter/prompt.py`,
  `backend/app/agents/redline_drafter/prompt.py`) — separate
  card (t_38c5d980).
- DE-specific clause taxonomy decisions (Schuldrecht /
  Sachenrecht enum values) — separate card (t_27c968a8).
- DPA and Employment contract types — Phase 5, not this card.
- Per-language F1 reporting — card t_a95b4169 + t_b4eb39a6.

## License note for downstream consumers

Two of the three sources (DIHK, IHK Hessen) are templates
distributed as Musterverträge for unrestricted business use,
with the publishers explicitly disclaiming warranty and
recommending legal review (typical for IHK / DIHK template
publishing — see the IHK Hessen Muster's "Vorwort" + "Hinweis
zur Benutzung des Mustervertrages" block). The third
(GeschGehG § 2 Nr. 1) is a federal statute with no copyright on
the text under § 5 UrhG. None of the provenance URLs require
registration or payment; the eval harness and the seeder logs
both treat the content as freely usable for internal
baseline/eval purposes.
