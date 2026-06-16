#!/usr/bin/env python3
"""Build a tracked-changes HTML view of demo/expected-redline.docx and
write it to docs/screenshots/sample-redline.html. The HTML is styled to
look like Word's tracked-changes view (strikethrough on deleted text,
red strikethrough, green insert) so the README's redline-output.png
shows the visible story of the redline.

The .docx itself only contains the final corrected text (the spec notes
this — mammoth doesn't render <w:ins>/<w:del>). So this script picks
the 5 most-recognisable deletion/insertion pairs out of the 5 demo
deviations and writes them as a stylized HTML document.
"""
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots" / "sample-redline.html"
OUT.parent.mkdir(parents=True, exist_ok=True)

# 5 deviation pairs from demo/expected-deviations.yaml.
# Each pair = (clause_id, heading, original_text, corrected_text, rationale).
PAIRS = [
    (
        "c1",
        "Definition of Confidential Information",
        "any and all information disclosed by one Party to the other Party, whether "
        "orally, in writing, or in any other form, without regard to whether such "
        "information is marked as confidential.",
        "non-public information designated as confidential at the time of disclosure, "
        "subject to four standard exclusions (public, prior knowledge, independently "
        "developed, lawfully required disclosure).",
        "missing_exclusions — baseline requires 4 standard carve-outs.",
    ),
    (
        "c2",
        "Term",
        "This Agreement shall remain in effect for a period of five (5) years. "
        "The obligations of confidentiality shall survive in perpetuity.",
        "This Agreement shall remain in effect for a period of two (2) years. "
        "The obligations of confidentiality shall survive for three (3) years "
        "post-termination.",
        "term_too_long — baseline is 2y + 3y survival; 5y + perpetual is material.",
    ),
    (
        "c3",
        "Residual Knowledge",
        "(no carve-out) The Receiving Party shall be bound by the full "
        "confidentiality obligation for any information disclosed.",
        "Nothing herein shall restrict the Receiving Party's use of general "
        "knowledge, skills, and experience retained in unaided memory by "
        "personnel who have had access to Confidential Information.",
        "missing_residual_knowledge_carveout — baseline requires the "
        "'unaided memory' qualifier.",
    ),
    (
        "c4",
        "Governing Law",
        "This Agreement shall be governed by the laws of the Cayman Islands. "
        "The Parties consent to the exclusive jurisdiction of the courts of "
        "the Cayman Islands.",
        "This Agreement shall be governed by the laws of the State of Delaware, "
        "without regard to conflict of laws principles. The Parties consent to "
        "the exclusive jurisdiction of the state and federal courts located in "
        "New Castle County, Delaware.",
        "offshore_jurisdiction — baseline is Delaware / New Castle County; "
        "Cayman Islands is a meaningful surprise for US/EU counterparties.",
    ),
    (
        "c5",
        "Remedies",
        "In no event shall either Party's aggregate liability exceed USD 50,000. "
        "Each Party expressly waives any right to seek injunctive or equitable relief.",
        "The Parties agree that monetary damages may be inadequate to remedy a "
        "breach, and the non-breaching Party shall be entitled to seek injunctive "
        "relief and other equitable remedies without the requirement of posting "
        "a bond or proving actual damages.",
        "damages_cap_in_lieu_of_injunction — baseline requires injunctive relief "
        "preserved; this is the only 'unacceptable' (score 3) deviation.",
    ),
]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_pair(idx, cid, heading, original, corrected, rationale):
    return f"""
  <p class="clause-id">{cid}</p>
  <h2>{idx}. {esc(heading)}</h2>
  <p class="redline">
    <s>{esc(original)}</s><strong>{esc(corrected)}</strong>
  </p>
  <p class="rationale">Rationale ({esc(cid)}, <code>{esc(rationale.split(' — ')[0])}</code>): {esc(rationale.split(' — ', 1)[1])}</p>"""


def main():
    css = """
  body { font-family: Georgia, serif; max-width: 760px; margin: 40px auto; padding: 20px;
         color: #1a1a1a; line-height: 1.6; background: white; }
  h1 { font-size: 22px; color: #2a2a2a; border-bottom: 1px solid #ddd; padding-bottom: 6px; }
  h2 { font-size: 16px; color: #2a2a2a; margin-top: 24px; }
  p { margin: 0.5em 0; }
  s { color: #b91c1c; text-decoration: line-through; }
  strong { color: #15803d; }
  em { color: #6b7280; font-size: 0.85em; }
  .clause-id { color: #6b7280; font-size: 0.78em; font-family: ui-monospace, monospace;
               margin: 0.3em 0 0 0; }
  .redline { background: #fafafa; border-left: 3px solid #ddd; padding: 8px 12px; }
  .rationale { color: #4b5563; font-size: 0.85em; font-style: italic; }
  code { background: #f3f4f6; padding: 1px 5px; border-radius: 3px; font-size: 0.9em; }
  .footer { margin-top: 40px; color: #6b7280; font-size: 0.85em; font-style: italic;
            border-top: 1px solid #ddd; padding-top: 12px; }
"""
    pairs_html = "\n".join(render_pair(i, *p) for i, p in enumerate(PAIRS, 1))
    body = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Expected redline — known-bad NDA</title><style>{css}</style></head>
<body>
<p>Mutual Non-Disclosure Agreement — Expected Redline</p>
<p><em>Effective Date: __________________</em></p>
<h1>Tracked changes (5 deviations, all approved)</h1>
{''.join(pairs_html)}
<p class="footer">--- This redline was generated by clausecraft (research / portfolio project). Not legal advice. See docs/LEGAL.md ---</p>
</body></html>
"""
    OUT.write_text(body, encoding="utf-8")
    print(f"  wrote {OUT} ({len(body)} bytes)")


if __name__ == "__main__":
    main()
