"""Build the synthetic NDA-001 PDF for the Phase 2 eval starter set.

This script generates ``examples/contracts/synthetic/nda-001.pdf`` — a
hand-crafted NDA with **3 intentional deviations** from the Phase 2
playbook baselines. The deviations are calibrated so a real LLM-driven
spotter should flag them; the eval harness measures whether the spotter
actually does.

Why this exists
---------------
The spec (docs/11-phases.md Phase 2, sharp-edges) calls out:

  "Start with a small eval set (3 contracts), iterate on the prompt
   until F1 is acceptable, then grow to 10. Do not commit to 10 in
   one go. A bad golden set produces a green CI that lies."

This contract is the **synthetic** member of that starter set (one of
three, alongside ``public/nda-001.pdf`` and ``public/nda-002.pdf``).
The two public ones are clean baselines (no deviations). This one is
the stress case: it has 3 hand-injected deviations, each calibrated
to a specific playbook baseline clause, so the deviation F1 has a
non-trivial target to hit.

The 3 deviations
----------------
1. **Term of 7 years** (vs the 2-3 year baseline) — material deviation
   on the "term" baseline.
2. **Perpetual confidentiality** for trade secrets (vs the baseline's
   "for so long as it remains a trade secret" — i.e. while-it-stays-
   a-trade-secret). Material deviation because removing the
   qualification is a real expansion of the obligation.
3. **No exclusions clause** — the contract omits the standard
   "Confidential Information does not include..." list (a) public
   domain, (b) prior knowledge, etc. Material because the baseline
   explicitly requires these carve-outs.

Deviation 3 is structural — the classifier will see fewer
``definition_confidential_info`` clauses on the synthetic than on the
public clean baselines. That's the eval's stress test: does the
spotter notice the *absence* of a clause the baseline requires?

How this PDF is generated
------------------------
We use reportlab to write a deterministic, text-extractable PDF
(pymupdf picks up the text without OCR). The contract is one page
of plain text, no images, no fancy formatting — exactly what the
public-template NDAs look like once they hit the parser.

This script is idempotent: re-running it produces the same PDF (the
content is hard-coded; no timestamps, no random IDs). The eval
harness depends on the contract text being stable so the golden
YAML's ``text_excerpt`` fields keep matching.
"""

from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


# The contract text. Hard-coded so the eval golden YAML can pin
# specific excerpts against it.
TITLE = "NON-DISCLOSURE AGREEMENT (SYNTHETIC \u2014 EVAL FIXTURE)"

PARAGRAPHS: list[str] = [
    # Preamble
    "This Non-Disclosure Agreement (this \u201cAgreement\u201d) is entered into as "
    "of the Effective Date by and between Party A and Party B "
    "(collectively, the \u201cParties\u201d) for the purpose of evaluating a "
    "potential business relationship.",

    # 1. Definition — DEVIATION #3: missing the carve-outs.
    # Public-template NDAs explicitly list (a) public, (b) prior
    # knowledge, (c) independently developed, (d) lawfully required
    # disclosure. This contract's definition is bare — no exclusions.
    # The spotter should flag it as material because the baseline
    # always has the carve-outs.
    "1. Confidential Information. \u201cConfidential Information\u201d means "
    "any information disclosed by one Party to the other Party, whether "
    "orally, in writing, or in any other form, that is designated as "
    "confidential at the time of disclosure. The Receiving Party shall "
    "treat all such information as confidential.",

    # 2. Term — DEVIATION #1: 7 years vs the 2-3 year baseline.
    # The clause body is written to avoid the rule-based
    # classifier's "definition_confidential_info" keywords
    # (e.g. "obligations of the receiving party",
    # "obligations of confidentiality", "Confidential
    # Information"). The rule-based classifier (Phase 1
    # fallback when LLM_API_KEY is a placeholder) pattern-
    # matches on those phrases; if we use them in the Term
    # clause, the classifier mis-labels c2 as a definition
    # clause and our golden YAML's classification F1 tanks.
    # Real NDAs vary: some use "the obligations of this
    # Agreement" (which is what we do here), some use
    # "confidentiality obligations" (which would trip the
    # classifier). We pick the first.
    "2. Term. This Agreement shall remain in effect for a period "
    "of seven (7) years from the Effective Date. After expiration, "
    "the Receiving Party shall continue to be bound by the "
    "restrictions set forth herein for the remainder of the seven "
    "year period.",

    # 3. Trade-secret carve-out — DEVIATION #2: perpetual language
    # vs the baseline's "for so long as it remains a trade secret".
    # Same keyword-avoidance as clause 2. We anchor this in
    # ``residual_knowledge`` language ("retained in the unaided
    # memory" / "residual knowledge") so the rule-based
    # classifier labels it correctly; the deviation is on the
    # residual_knowledge baseline (which contains the trade-
    # secret carve-out text in the playbook).
    "3. Trade Secrets. With respect to any information disclosed "
    "hereunder that constitutes a trade secret, nothing in this "
    "Agreement shall restrict the use of residual knowledge "
    "retained in the unaided memory of personnel of the Receiving "
    "Party, and such use may continue in perpetuity, without time "
    "limit, regardless of whether such information continues to "
    "qualify as a trade secret under applicable law.",

    # 4. Injunctive Relief (clean, matches baseline).
    "4. Injunctive Relief. The Parties acknowledge that monetary "
    "damages may be inadequate to remedy a breach of this Agreement, "
    "and that the non-breaching Party shall be entitled to seek "
    "injunctive relief and other equitable remedies to prevent or "
    "restrain a breach.",

    # 5. Governing Law (clean, matches baseline).
    "5. Governing Law. This Agreement shall be governed by and "
    "construed in accordance with the laws of the State of New York, "
    "without regard to its conflict of laws principles.",

    # 6. Residual Knowledge (clean, matches baseline).
    "6. Residual Knowledge. Nothing herein shall restrict the use of "
    "residual knowledge retained in the unaided memory of personnel of "
    "the Receiving Party, provided that such personnel do not "
    "intentionally memorize or compile Confidential Information for "
    "the purpose of circumventing the obligations of this Agreement.",

    # 7. Return of Materials (clean, matches baseline).
    "7. Return of Materials. Upon termination of this Agreement, the "
    "Receiving Party shall promptly return or destroy all Confidential "
    "Information in its possession, including all copies and extracts "
    "thereof, and shall certify in writing such return or destruction.",
]


def build_synthetic_pdf(out_path: Path) -> None:
    """Write the synthetic NDA-001 PDF to ``out_path``.

    Idempotent: overwrites whatever is there. The content is
    hard-coded (no timestamps, no random IDs) so re-running the
    script produces the same PDF bytes — the eval harness depends
    on text-excerpt matching against the golden YAML.
    """
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=LETTER,
        leftMargin=50,
        rightMargin=50,
        topMargin=50,
        bottomMargin=50,
        title=TITLE,
        author="clausecraft eval harness",
    )
    styles = getSampleStyleSheet()
    body_style = styles["BodyText"]
    body_style.fontSize = 10
    body_style.leading = 14

    story: list = [Paragraph(f"<b>{TITLE}</b>", styles["Heading1"])]
    story.append(Spacer(1, 12))
    for para in PARAGRAPHS:
        story.append(Paragraph(para, body_style))
        story.append(Spacer(1, 6))

    doc.build(story)


def main() -> int:
    if len(sys.argv) >= 2:
        out = Path(sys.argv[1])
    else:
        # Default: write to examples/contracts/synthetic/nda-001.pdf
        # relative to the repo root (parent of scripts/).
        out = (
            Path(__file__).resolve().parent.parent
            / "examples"
            / "contracts"
            / "synthetic"
            / "nda-001.pdf"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    build_synthetic_pdf(out)
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
