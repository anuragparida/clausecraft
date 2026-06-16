"""Build the counterfactual demo NDA PDF (clausecraft Phase 6).

This script generates ``demo/known-bad-nda.pdf`` — a hand-crafted
mutual NDA with **5 intentional deviations** from the Phase 2
playbook baselines. The deviations are calibrated so a real
LLM-driven spotter should flag all 5; the eval harness measures
whether the spotter actually does.

Why this exists
---------------
Phase 6 (the polish + deploy + demo phase) needs a
**counterfactual demo contract** that the asciinema screencast
runs against. The spec (docs/11-phases.md § "Phase 6") calls this
"the single most-watched artifact" — the demo is reproducible if
the contract is reproducible, and it's reproducible only if the
PDF is generated deterministically and the deviations are
documented end-to-end.

The 5 deviations
----------------
Each deviation is calibrated to a specific Phase 2 playbook
baseline clause. The deviations are stacked into a single NDA
so the asciinema can show a 5-row deviation table in one shot
(Phase 2 golden sets typically have 2-3 deviations per
contract; this one has 5 because the asciinema's "wow" moment
is the moment 5 rows light up at once).

1. **c1 (definition_confidential_info) — Material.**
   "All information disclosed" with no exclusions list (vs the
   baseline's 4 standard carve-outs: public domain, prior
   knowledge, independently developed, lawfully required). The
   spotter should flag this as material because the baseline
   explicitly requires the carve-outs.

2. **c2 (term) — Material.**
   5 years obligation + 5 year survival = 10 years total, plus
   perpetual trade-secret protection (vs the baseline's 2 year
   obligation + 3 year survival + trade-secret-while-it-remains-
   a-trade-secret). The spotter should flag this as material
   because the longer term and perpetual trade-secret expansion
   exceed the playbook's reference.

3. **c3 (residual_knowledge) — Material.**
   No residual knowledge carve-out at all (vs the baseline's
   "unaided memory" qualifier). Without the carve-out, the
   Receiving Party's employees could be contractually barred
   from doing their own jobs. The spotter should flag this as
   material because the baseline always has the carve-out.

4. **c4 (governing_law) — Material.**
   Cayman Islands law, exclusive jurisdiction in the courts of
   the Cayman Islands (vs the baseline's Delaware / New Castle
   County). Cayman Islands is a meaningful surprise for a US/
   EU counterparty — the deviation is the off-shore choice, not
   the geographic location. Material because it changes the
   dispute-resolution venue from the playbook's reference.

5. **c5 (injunctive_relief) — Unacceptable.**
   Caps damages at USD 50,000 and explicitly disclaims
   injunctive relief (vs the baseline's equitable relief
   carve-out — the teeth of the NDA). This is the only
   deviation that's "unacceptable" (score 3) rather than
   "material" (score 2) because it removes the only remedy
   that actually deters a breach: an injunction.

How this PDF is generated
-------------------------
We use reportlab to write a deterministic, text-extractable PDF
(pymupdf picks up the text without OCR). The contract is one page
of plain text, no images, no fancy formatting — exactly what the
public-template NDAs look like once they hit the parser.

This script is idempotent: re-running it produces the same PDF
(the content is hard-coded; no timestamps, no random IDs). The
asciinema's reproducibility depends on the contract text being
stable so the demo's deviation table renders the same way every
time.

Relation to other eval contracts
--------------------------------
- ``examples/contracts/synthetic/nda-001.pdf`` — synthetic
  Phase 2 starter (3 deviations, stress test)
- ``examples/contracts/hand-curated/nda-001.pdf`` — hand-
  curated Phase 2 starter (2 deviations, realism test)
- ``examples/contracts/phase1_test/aba-mutual-nda.pdf`` —
  public-source clean baseline (0 deviations)
- ``demo/known-bad-nda.pdf`` (this script's output) — Phase 6
  counterfactual demo (5 deviations, "wow" moment)

The demo contract lives in ``demo/`` rather than
``examples/`` because it's a demo artifact, not an eval
fixture. The eval fixtures drive the harness; the demo drives
the asciinema. Both have expected-deviation YAMLs in the same
shape, but they're consumed by different tools.
"""

from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


# The contract text. Hard-coded so the eval golden YAML and the
# asciinema both pin specific excerpts against it. Every
# deviation is annotated with [DEVIATION #N: <name>] so the
# commentary lines up with the deviation table the system
# produces.
TITLE = "MUTUAL NON-DISCLOSURE AGREEMENT"

PARAGRAPHS: list[str] = [
    # Preamble (clean — no deviation).
    "This Mutual Non-Disclosure Agreement (this \u201cAgreement\u201d) is "
    "entered into as of the Effective Date by and between "
    "_________________________, a Delaware corporation "
    "(\u201cDiscloser\u201d), and _________________________ "
    "(\u201cRecipient\u201d) (collectively, the \u201cParties\u201d) for the "
    "purpose of evaluating a potential business relationship.",

    # 1. Definition — DEVIATION #1 (Material, category: missing_exclusions).
    # Baseline: 4 standard carve-outs (public, prior knowledge,
    # independently developed, lawfully required). This contract:
    # bare "all information" with NO carve-outs. The spotter should
    # flag this as material because the baseline always has the
    # exclusions list.
    "1. Definition of Confidential Information. "
    "\u201cConfidential Information\u201d means any and all information "
    "disclosed by one Party to the other Party, whether orally, in "
    "writing, or in any other form, without regard to whether such "
    "information is marked as confidential. The Receiving Party "
    "shall treat all such information as confidential and shall be "
    "bound by the obligations of this Agreement with respect to "
    "all such information without limitation.",

    # 2. Term — DEVIATION #2 (Material, category: term_too_long).
    # Baseline: 2 year obligation + 3 year survival. This contract:
    # 5 year obligation + 5 year survival = 10 years total. The
    # spotter should flag this as material because the longer term
    # expands the Receiving Party's restriction window.
    "2. Term. This Agreement shall commence on the Effective Date "
    "and shall continue for a period of five (5) years thereafter, "
    "unless earlier terminated in accordance with its terms. The "
    "obligations of confidentiality and non-use set forth in this "
    "Agreement shall survive the termination or expiration of this "
    "Agreement for an additional period of five (5) years, "
    "totalling ten (10) years of confidentiality obligations.",

    # 3. Residual Knowledge — DEVIATION #3 (Material, category:
    # missing_residual_knowledge_carveout). Baseline: explicit
    # "unaided memory" carve-out. This contract: no carve-out
    # whatsoever — the Receiving Party's employees are bound by
    # the full confidentiality obligation, even for information
    # that remains in their unaided memory.
    "3. Trade Secret Protection. With respect to any information "
    "disclosed hereunder that constitutes a trade secret, the "
    "Receiving Party and its personnel shall be bound by the "
    "obligations of confidentiality and non-use set forth in this "
    "Agreement in perpetuity, without time limit, regardless of "
    "whether such information continues to qualify as a trade "
    "secret under applicable law.",

    # 4. Governing Law — DEVIATION #4 (Material, category:
    # offshore_jurisdiction). Baseline: Delaware. This contract:
    # Cayman Islands. Material because it changes the dispute-
    # resolution venue from the playbook's reference and adds the
    # burden of off-shore litigation for either Party.
    "4. Governing Law. This Agreement shall be governed by and "
    "construed in accordance with the laws of the Cayman Islands, "
    "without giving effect to any choice-of-law or conflict-of-laws "
    "provision that would cause the laws of any other jurisdiction "
    "to apply. The Parties consent to the exclusive jurisdiction of "
    "the courts of the Cayman Islands for any action arising out of "
    "or relating to this Agreement.",

    # 5. Injunctive Relief — DEVIATION #5 (Unacceptable, category:
    # damages_cap_in_lieu_of_injunction). Baseline: equitable
    # relief carve-out + no bond. This contract: USD 50,000 cap +
    # explicit disclaimer of injunctive relief. Unacceptable
    # (score 3) because it removes the only remedy that actually
    # deters a breach.
    "5. Remedies. The Parties agree that the sole and exclusive "
    "remedy for any breach of this Agreement shall be monetary "
    "damages, capped at a maximum aggregate liability of fifty "
    "thousand United States dollars (USD 50,000). The Parties "
    "expressly waive any right to seek injunctive relief, "
    "specific performance, or other equitable remedies in "
    "connection with this Agreement.",

    # 6. Return of Materials (clean — matches baseline).
    "6. Return of Materials. Upon termination of this Agreement, "
    "the Receiving Party shall promptly return or destroy all "
    "Confidential Information in its possession, including all "
    "copies and extracts thereof, and shall certify in writing "
    "such return or destruction.",

    # 7. Entire Agreement (clean — boilerplate, no deviation).
    "7. Entire Agreement. This Agreement constitutes the entire "
    "agreement of the Parties with respect to the subject matter "
    "hereof and supersedes all prior or contemporaneous "
    "agreements, understandings, negotiations, and discussions, "
    "whether oral or written, between the Parties with respect to "
    "such subject matter.",
]


def build_pdf(output_path: Path) -> None:
    """Build ``demo/known-bad-nda.pdf`` from the hard-coded text."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        leftMargin=1 * inch,
        rightMargin=1 * inch,
        topMargin=1 * inch,
        bottomMargin=1 * inch,
        title="Mutual NDA — Counterfactual Demo (Phase 6)",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Title"],
        fontSize=14,
        spaceAfter=18,
        alignment=1,  # center
    )
    body_style = ParagraphStyle(
        "BodyStyle",
        parent=styles["BodyText"],
        fontSize=10,
        leading=14,
        spaceAfter=10,
        alignment=4,  # justified
    )

    story = [Paragraph(TITLE, title_style), Spacer(1, 0.2 * inch)]
    for para in PARAGRAPHS:
        story.append(Paragraph(para, body_style))

    doc.build(story)
    print(f"Built {output_path} ({output_path.stat().st_size} bytes)")


if __name__ == "__main__":
    # Default: write to demo/known-bad-nda.pdf relative to repo root.
    repo_root = Path(__file__).resolve().parent.parent
    output = repo_root / "demo" / "known-bad-nda.pdf"
    if len(sys.argv) > 1:
        output = Path(sys.argv[1])
    build_pdf(output)
