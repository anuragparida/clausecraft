# Public DE Employment Eval Contracts — Sources

This document records the provenance for every German-language
**employment** contract shipped under `examples/contracts/public-de/`.
The card's hard rule (t_ccb0a7fd): "real public source per
contract, provenance in metadata. Match the playbook's SOURCES.md
discipline." Every public-DE employment contract here traces to
a public source that is independently citable and verifiable.
Retrieval date for all three sources is 2026-06-15.

The NDA SOURCES for `examples/contracts/public-de/` (covering
`nda-001.pdf`, `nda-002.pdf`, `nda-003.pdf`) live in this
directory's `SOURCES.md` file (card t_b238eff4). This file
covers only the employment contracts.

## Source summary

| File | Source | Source kind | Why it's a public source |
|---|---|---|---|
| `employment-001.pdf` | [IHK Musterarbeitsvertrag Januar 2025](https://www.ihk.de/blueprint/servlet/resource/blob/764306/02ef8855772d2df8a4c743b497776f4d/arbeitsvertrag-muster--data.pdf) (§ 12, § 13) | IHK model template | The same IHK template the DE Employment baselines card (t_84896561) anchored for non-solicitation. Here it anchors § 12 (Wettbewerbsverbot ohne Karenzentschädigung) + § 13 (Freistellung). |
| `employment-002.pdf` | [BGB § 74 HGB](https://www.gesetze-im-internet.de/hgb/__74.html) (Karenzentschädigung 50%) | Federal statute (BMJ/BfJ juristic portal) | The statutory anchor for nachvertragliches Wettbewerbsverbot with 50% Karenzentschädigung. Published on the official BMJV juristic portal, no copyright on the statute text (§ 5 UrhG). |
| `employment-003.pdf` | [Arbeitnehmererfindungsgesetz (ArbEG)](https://www.gesetze-im-internet.de/arbeg/index.html) (§ 4, § 6, § 9, § 15, § 18) | Federal statute (BMJ/BfJ juristic portal) | The statutory anchor for DE IP-Assignment. Diensterfindung Meldepflicht (§ 4), Inanspruchnahme-Frist (§ 6), Vergütungsanspruch (§ 9 + § 15), Freie-Erfindungen-Meldepflicht (§ 18). |

**Three public-DE employment contracts, three distinct source
hosts (1× IHK, 2× BMJ juristic portal). The IHK template
mirrors the DE baselines card's source spread (1× IHK + 4×
Bundesgesetzestexte); the BGB § 74 HGB anchor is the same
statute the DE baselines used for non-solicitation, here
re-purposed for the non_compete GAP.md value with the
Karenzentschädigung economic shape.**

## Per-contract notes

### `employment-001.pdf` — IHK Musterarbeitsvertrag Januar 2025 (§ 12, § 13)

The contract text uses the IHK model template's § 12
(Wettbewerbsverbot — 12 Monate, ohne Karenzentschädigung, weil
Verbotsdauer = Beschäftigungsdauer) and § 13 (Freistellung —
unbeschränkte Freistellung mit Vergütungsfortzahlung) verbatim.
This is the load-bearing DE `garden_leave` + `non_compete`
taxonomy anchor for Phase 5.

### `employment-002.pdf` — BGB § 74 HGB nachvertragliches Wettbewerbsverbot

The contract follows § 74 HGB: 24-month prohibition, 50%
Karenzentschädigung der letzten Bezüge, monatliche Fälligkeit
(§ 74 Abs. 3 HGB), 6-Monats-Ablehnungsfrist des Arbeitnehmers
(§ 75 HGB). This is the load-bearing DE `non_compete`
taxonomy anchor for Phase 5 — the "with Karenzentschädigung"
economic variant, complementing the IHK "without
Karenzentschädigung" variant in #1.

### `employment-003.pdf` — ArbEG Diensterfindungen

The contract follows the ArbEG framework: 4-month
Inanspruchnahme window for Diensterfindungen (§ 6 Abs. 1
ArbEG), Vergütung calculated per § 15 ArbEG (wirtschaftliche
Verwertbarkeit, Aufgabenstellung, Unternehmensanteil), Freie
Erfindungen separately meldepflichtig per § 18 ArbEG. This is
the load-bearing DE `ip_assignment` taxonomy anchor for
Phase 5 — the DE counterpart of the US California Labor
Code § 2870 carve-out framework.

## License note for downstream consumers

The IHK source is a model template distributed as a
Mustervertrag for unrestricted business use, with the
publisher explicitly disclaiming warranty and recommending
legal review (typical for IHK template publishing). The
two federal statutes (BGB § 74 HGB and ArbEG) are published
on the official BMJV juristic portal with no copyright on
the statute text under § 5 UrhG. None of the provenance
URLs require registration or payment; the eval harness and
the seeder treat the content as freely usable for internal
baseline/eval purposes.
