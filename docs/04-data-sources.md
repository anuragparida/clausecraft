# 04 — Data Sources

> Public playbook sources, golden eval contracts, what we use and what we never commit.

**Status:** stub. Critical IP-safety doc.

## Playbook sources (public, citable)

### English

- **NDA:** ABA Model Mutual NDA, SEC sample, IAPP NDA templates
- **DPA:** EU Standard Contractual Clauses (Commission Decision 2021/914), IAPP sample DPAs, EDPB recommendations
- **Employment:** US at-will templates (state-specific), UK statement of particulars (gov.uk), ACAS samples

### German

- **NDA:** Vertragsmuster.de (BMJ), IHK Musterverträge, BGH standard formulations
- **DPA:** EU SCCs (German version, BAnz), DSGVO Art 28 text, BDSG, DSK Kurzpapier
- **Employment:** Tarifvertrag references (BAP, IG Metall), BGB §§ 611a ff., Kündigungsschutzgesetz, Nachweisgesetz, IHK Musterarbeitsvertrag

## Golden eval set (10-20 contracts, hand-labeled deviations)

Sourcing decision pending (see open questions in main planning conversation):

- **(a) Public templates only** — clean baselines, deviations are injected
- **(b) Real anonymized public contracts** — court filings, government procurement
- **(c) LLM-generated synthetic contracts** — fast but reviewer-skeptical

My pick: **(a) for v1, (b) for v2.**

## What we NEVER commit

- Real client contracts (even redacted — redaction is brittle)
- Internal HDI / Mercedes / Zepto contracts or templates
- Proprietary "best practices" (these live in a gitignored config file if used at all)
- Anything with PII, deal terms, party names

## What we DO commit

- Public-source playbook clauses, with provenance (URL + retrieval date + license)
- Synthetic eval contracts, clearly labeled as synthetic
- Hand-labeled expected deviations in YAML, with the rationale for each label
- Langfuse dataset IDs for the eval set

## License posture

- **Project code:** Apache 2.0 (per seed spec)
- **Playbook clauses:** each source's license respected; mostly CC-BY or public domain
- **Eval contracts:** synthetic = ours; public = source's license

## Open questions for this doc

- For DE employment contracts, is the Tarifvertrag reference the right baseline, or do we need per-Branche baselines? (My take: per-Branche is too granular for v1. Use the generic BGB baseline + a note that branch-specific deviations may be intentional.)
- For DPAs, do we seed with the 2021 SCCs only, or include the older 2010 SCCs as legacy baselines? (My take: 2021 only, with a deprecation note for 2010.)
