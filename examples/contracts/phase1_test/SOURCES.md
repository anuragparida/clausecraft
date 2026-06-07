# Test contracts for Phase 1

This directory contains the 5 NDA contracts used by the Phase 1 exit-gate tests. None of them are real, signed agreements. All sources are clearly identified below.

## Files

| File | Profile | Source | License |
|---|---|---|---|
| `aba-mutual-nda.pdf` | Public-source mutual NDA template, clean baseline (3 pages, numbered sections like "1. Either Party may disclose..."). | https://nondisclosureagreement.com/wp-content/uploads/2018/03/Mutual-Non-Disclosure-Agreement.pdf | Public template, free to download and use; no copyright notice on the source page. |
| `weird-format-nda.pdf` | Synthetic. ALL-CAPS section headers ("CONFIDENTIALITY.", "OBLIGATIONS OF THE RECEIVING PARTY.", "TERM.", "GOVERNING LAW."), no numbered sections. Generated from an inline string at test setup time. | n/a (synthetic) | n/a |
| `short-nda.pdf` | Synthetic. 1-page, 3 numbered clauses ("1. Confidential Information. ...", "2. Term. ...", "3. Governing Law. ..."). | n/a (synthetic) | n/a |
| `long-nda.pdf` | Synthetic. 17 pages, deeply numbered sections like "1.1.1", "1.2.3", up through "15.3.3", plus a definitions + return of materials + term + governing law + entire agreement + notices + severability + counterparts + assignment + injunctive relief + residual knowledge + limitation of liability + non-solicitation block. | n/a (synthetic) | n/a |
| `scanned-style-nda.pdf` | Synthetic. The weird-format NDA rendered as page images (DPI 150) and re-embedded into a new PDF with no text layer. The PDF is a real PDF (header / xref / etc.) but the text-layer is empty. Expected to trip the `is_scanned_pdf` threshold and return warnings + minimal clause text. | n/a (synthetic, derived from `weird-format-nda.pdf`) | n/a |

## Why "ABA" instead of the real ABA template

The American Bar Association publishes model NDA forms, but the most-cited public template is on `nondisclosureagreement.com`, which mirrors the ABA form's structure. We use the public template here because (a) the ABA itself does not host a clean PDF download of the model form, and (b) the source page is free, public, and unmodified. The "ABA Model Mutual NDA" slot in the spec is satisfied by a template of equivalent structure (mutual NDA, 3 pages, clean numbered sections). If a strict ABA-provenance fixture is needed for Phase 2, swap this file for a copy of the ABA source and update the table above.

## How the tests use these files

`tests/phase1/test_ingest_contracts.py` runs `app.pipeline.run_stage1` against each file in this directory and asserts:

1. No exception is thrown.
2. ≥80 % of clauses get a non-null `type` (i.e. not `unknown`).
3. The returned JSON shape matches the `Clause` Pydantic model.
4. The `is_scanned` flag is `True` only for `scanned-style-nda.pdf`.

Run the suite from the repo root with `pytest tests/phase1/`.

## Provenance + integrity

These files are committed to the repo for reproducibility. If a real contract ever ends up in this directory by accident, remove it immediately — the hard rule in the Phase 1 card is "no real contracts committed". The `.gitignore` at the repo root will block PDFs larger than 10 MB from accidental commits, but the gate is the human, not the tool.
