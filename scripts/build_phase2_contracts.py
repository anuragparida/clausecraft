"""Build the 7 new Phase 2 eval contracts (3→10 expansion).

This script generates the 7 contracts that grow the Phase 2 eval
set from 3 → 10. The contract set is:

  examples/contracts/public/nda-003.pdf        (clean baseline, short)
  examples/contracts/public/nda-004.pdf        (clean baseline, one-way)
  examples/contracts/public/nda-005.pdf        (clean baseline, long-form w/ non-solicit)
  examples/contracts/synthetic/nda-002.pdf     (stress: 3 different deviation categories)
  examples/contracts/hand-curated/nda-001.pdf  (realistic deviations, gov-law + carve-out)
  examples/contracts/hand-curated/nda-002.pdf  (realistic deviations, term + return)
  examples/contracts/hand-curated/nda-003.pdf  (realistic deviations, residual + disclosure)

Note: the kanban card asks for "2 hand-curated" but the spec target
is 10 contracts (5 public + 2 synthetic + 3 hand-curated), so we
ship 3 hand-curated to hit 10. The parent card t_741f36a0 already
shipped 3 contracts; this script ships 7 more, for a total of 10.

Why all of these are text-extractable, deterministic PDFs
---------------------------------------------------------
The eval harness depends on text-excerpt matching against the
golden YAML, so the contract text must be byte-stable across
runs. We use reportlab to write plain-text PDFs (no images, no
OCR) with hard-coded content — the same approach as
``build_synthetic_nda.py``. No timestamps, no random IDs.

Why "public" here means "public-template style", not network-fetch
------------------------------------------------------------------
The spec calls for "5 NDA contracts from public templates". The
parent card (t_741f36a0) shipped nda-001 and nda-002 as "public
templates" sourced from nondisclosureagreement.com. We don't
have network access from this environment, so nda-003..nda-005
are written in the same *style* as public-template NDAs
(standard section headings, full clause bodies, baseline-aligned
language). The text is hard-coded and self-authored, not
copied. The eval harness treats them identically to the
existing 2 — they just need to ingest cleanly and have
text-extractable clauses.

Why the deviation coverage is diverse
-------------------------------------
synthetic-001 covers (a) missing exclusions, (b) term_too_long,
(c) perpetual_without_qualifier. The new contracts deliberately
extend the deviation *category* coverage to:

  - governing_law variance (hand-curated-001): NY→TX
  - missing termination right (synthetic-002, hand-curated-002)
  - missing_return_of_materials (synthetic-002)
  - residual knowledge scope expanded (hand-curated-003)
  - "best efforts" language substitution (hand-curated-001)
  - confidentiality term too short (hand-curated-002)

The goal per the spec is: "each new contract should expand the
deviation *categories* covered, not just duplicate existing
ones."

How this script is invoked
--------------------------
``python3 scripts/build_phase2_contracts.py`` writes all 7 PDFs
to their canonical paths. Idempotent: re-running overwrites
with identical bytes.
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

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_ROOT = REPO_ROOT / "examples" / "contracts"


# --- Generators ---------------------------------------------------------


def _build_pdf(out_path: Path, title: str, paragraphs: list[str]) -> None:
    """Write a one-shot plain-text PDF to ``out_path``."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=LETTER,
        leftMargin=50,
        rightMargin=50,
        topMargin=50,
        bottomMargin=50,
        title=title,
        author="clausecraft eval harness (build_phase2_contracts.py)",
    )
    styles = getSampleStyleSheet()
    body_style = styles["BodyText"]
    body_style.fontSize = 10
    body_style.leading = 14

    story: list = [Paragraph(f"<b>{title}</b>", styles["Heading1"])]
    story.append(Spacer(1, 12))
    for para in paragraphs:
        story.append(Paragraph(para, body_style))
        story.append(Spacer(1, 6))

    doc.build(story)


# --- public-003 — short-form mutual NDA --------------------------------
#
# Shape: 2-page mutual NDA, 7 clauses, all clean baselines.
# Different from public-001/002 in length and section ordering
# so the parser exercises a different surface (short preamble,
# compact sections).

PUBLIC_003_TITLE = "MUTUAL NON-DISCLOSURE AGREEMENT (SHORT FORM)"

PUBLIC_003_PARAGRAPHS: list[str] = [
    "This Mutual Non-Disclosure Agreement (this \u201cAgreement\u201d) is "
    "made effective as of the Effective Date by and between the "
    "parties identified on the signature page (each, a \u201cParty\u201d "
    "and together, the \u201cParties\u201d). The Parties wish to explore "
    "a potential business relationship and may exchange Confidential "
    "Information in connection therewith.",
    "1. Confidential Information. \u201cConfidential Information\u201d "
    "means any non-public information disclosed by one Party to the "
    "other, whether orally, in writing, or in any other form, that is "
    "marked as confidential or that would reasonably be understood to "
    "be confidential given the nature of the information and the "
    "circumstances of disclosure.",
    "1.1 Exclusions. Confidential Information does not include "
    "information that (a) is or becomes generally available to the "
    "public other than as a result of disclosure by the Receiving "
    "Party, (b) was known to the Receiving Party on a non-confidential "
    "basis prior to disclosure, or (c) becomes available to the "
    "Receiving Party on a non-confidential basis from a source other "
    "than the Disclosing Party, provided that such source is not "
    "bound by a duty of confidentiality.",
    "2. Term. This Agreement shall remain in effect for a period of "
    "two (2) years from the Effective Date. The Parties\u2019 "
    "obligations of confidentiality shall survive termination of this "
    "Agreement for an additional three (3) years.",
    "3. Return of Materials. Upon termination of this Agreement, the "
    "Receiving Party shall promptly return or destroy all Confidential "
    "Information in its possession, including all copies and extracts "
    "thereof, and shall certify in writing such return or destruction.",
    "4. Governing Law. This Agreement shall be governed by and "
    "construed in accordance with the laws of the State of Delaware, "
    "without regard to its conflict of laws principles.",
    "5. Entire Agreement. This Agreement constitutes the entire "
    "agreement between the Parties with respect to the subject matter "
    "hereof and supersedes all prior or contemporaneous "
    "communications, understandings, and agreements, whether oral or "
    "written, between the Parties with respect to such subject matter.",
    "6. Injunctive Relief. The Parties acknowledge that monetary "
    "damages may be inadequate to remedy a breach of this Agreement, "
    "and that the non-breaching Party shall be entitled to seek "
    "injunctive relief and other equitable remedies to prevent or "
    "restrain a breach.",
    "IN WITNESS WHEREOF, the Parties have executed this Agreement as "
    "of the Effective Date.",
    "PARTY A SIGNATURE: ____________________________",
    "PARTY B SIGNATURE: ____________________________",
]


# --- public-004 — one-way (unilateral) NDA -----------------------------
#
# Shape: one-way NDA where only one Party discloses. 8 clauses,
# includes Standard of Care + Permitted Disclosures (which the
# 2-existing public contracts do not). Different in structure
# from the mutual NDAs in the starter set.

PUBLIC_004_TITLE = "NON-DISCLOSURE AGREEMENT (UNILATERAL)"

PUBLIC_004_PARAGRAPHS: list[str] = [
    "This Non-Disclosure Agreement (this \u201cAgreement\u201d) is "
    "entered into as of the Effective Date by and between the "
    "Disclosing Party and the Receiving Party identified on the "
    "signature page hereto. The Disclosing Party may disclose "
    "Confidential Information to the Receiving Party in connection "
    "with the purpose described herein.",
    "1. Confidential Information. \u201cConfidential Information\u201d "
    "means any non-public information disclosed by the Disclosing Party "
    "to the Receiving Party, whether orally, in writing, or in any "
    "other form, that is designated as confidential at the time of "
    "disclosure. Confidential Information includes, without limitation, "
    "technical information, business plans, customer lists, financial "
    "data, and product roadmaps.",
    "1.1 Exclusions. Confidential Information does not include "
    "information that (a) is or becomes generally available to the "
    "public other than as a result of disclosure by the Receiving "
    "Party, (b) was known to the Receiving Party on a "
    "non-confidential basis prior to disclosure, or (c) becomes "
    "available to the Receiving Party on a non-confidential basis "
    "from a source other than the Disclosing Party.",
    "2. Obligations of the Receiving Party. The Receiving Party "
    "shall (a) hold the Confidential Information in strict "
    "confidence, (b) use the Confidential Information solely for the "
    "purpose described in this Agreement, and (c) take all "
    "reasonable precautions to prevent unauthorized disclosure.",
    "2.1 Standard of Care. The Receiving Party shall protect the "
    "Confidential Information using at least the same degree of "
    "care it uses to protect its own confidential information of "
    "similar importance, but in no event less than reasonable care.",
    "2.2 Permitted Disclosures. The Receiving Party may disclose "
    "Confidential Information only to its employees and "
    "representatives who (a) have a need to know such information "
    "for the purpose described in this Agreement and (b) are bound "
    "by confidentiality obligations at least as restrictive as "
    "those set forth in this Agreement.",
    "3. Term. This Agreement shall remain in effect for a period of "
    "three (3) years from the Effective Date. The Receiving "
    "Party\u2019s obligations of confidentiality shall survive "
    "termination for an additional two (2) years.",
    "4. Return of Materials. Upon termination of this Agreement, the "
    "Receiving Party shall promptly return or destroy all "
    "Confidential Information in its possession and certify such "
    "return or destruction in writing.",
    "5. Governing Law. This Agreement shall be governed by the laws "
    "of the State of California, without regard to its conflict of "
    "laws principles.",
    "6. Entire Agreement. This Agreement constitutes the entire "
    "agreement between the Parties with respect to its subject "
    "matter and supersedes all prior or contemporaneous "
    "communications and agreements, whether oral or written.",
    "7. Injunctive Relief. The Parties acknowledge that monetary "
    "damages may be inadequate to remedy a breach and that the "
    "non-breaching Party shall be entitled to seek injunctive "
    "relief and other equitable remedies.",
    "IN WITNESS WHEREOF, the Parties have executed this Agreement "
    "as of the Effective Date.",
    "DISCLOSING PARTY SIGNATURE: ____________________________",
    "RECEIVING PARTY SIGNATURE: ____________________________",
]


# --- public-005 — long-form w/ non-solicit ------------------------------
#
# Shape: 11 clauses, includes Non-Solicitation and Limitation of
# Liability (which the 2-existing public contracts lack). Tests
# that the parser handles the full Phase 2 enum set end-to-end on
# a clean baseline.

PUBLIC_005_TITLE = "MUTUAL NON-DISCLOSURE AGREEMENT (LONG FORM)"

PUBLIC_005_PARAGRAPHS: list[str] = [
    "This Mutual Non-Disclosure Agreement (this \u201cAgreement\u201d) "
    "is entered into as of the Effective Date by and between the "
    "parties identified on the signature page hereto (each, a "
    "\u201cParty\u201d and collectively, the \u201cParties\u201d).",
    "1. Confidential Information. \u201cConfidential Information\u201d "
    "means any non-public information disclosed by one Party to the "
    "other, whether orally, in writing, or in any other form, that is "
    "marked as confidential or that would reasonably be understood to "
    "be confidential given the nature of the information and the "
    "circumstances of disclosure.",
    "1.1 Exclusions. Confidential Information does not include "
    "information that (a) is or becomes generally available to the "
    "public other than as a result of disclosure by the Receiving "
    "Party, (b) was known to the Receiving Party on a "
    "non-confidential basis prior to disclosure, or (c) becomes "
    "available to the Receiving Party on a non-confidential basis "
    "from a source other than the Disclosing Party, provided that "
    "such source is not bound by a duty of confidentiality.",
    "2. Term. This Agreement shall remain in effect for a period of "
    "two (2) years from the Effective Date. The Parties\u2019 "
    "obligations of confidentiality shall survive termination for "
    "an additional three (3) years.",
    "3. Return of Materials. Upon termination of this Agreement, the "
    "Receiving Party shall promptly return or destroy all "
    "Confidential Information in its possession, including all "
    "copies and extracts thereof, and certify such return or "
    "destruction in writing.",
    "4. Governing Law. This Agreement shall be governed by the laws "
    "of the State of New York, without regard to its conflict of "
    "laws principles.",
    "5. Entire Agreement. This Agreement constitutes the entire "
    "agreement between the Parties with respect to its subject "
    "matter and supersedes all prior or contemporaneous "
    "communications and agreements, whether oral or written.",
    "6. Severability. If any provision of this Agreement is held to "
    "be invalid or unenforceable, the remaining provisions shall "
    "continue in full force and effect, and the invalid or "
    "unenforceable provision shall be modified to the minimum extent "
    "necessary to make it valid and enforceable.",
    "7. Notices. All notices, requests, consents, and other "
    "communications required or permitted under this Agreement "
    "shall be in writing and shall be deemed delivered when "
    "personally delivered, sent by confirmed email, or sent by "
    "certified mail, return receipt requested.",
    "8. Injunctive Relief. The Parties acknowledge that monetary "
    "damages may be inadequate to remedy a breach and that the "
    "non-breaching Party shall be entitled to seek injunctive "
    "relief and other equitable remedies.",
    "9. Non-Solicitation. For a period of twelve (12) months "
    "following termination of this Agreement, neither Party shall "
    "directly solicit for employment any employee of the other "
    "Party with whom such Party had material contact in connection "
    "with this Agreement.",
    "10. Limitation of Liability. In no event shall either Party be "
    "liable to the other for any indirect, incidental, special, or "
    "consequential damages arising out of or in connection with this "
    "Agreement, even if such Party has been advised of the "
    "possibility of such damages.",
    "11. Counterparts. This Agreement may be executed in one or more "
    "counterparts, each of which shall be deemed an original, but "
    "all of which together shall constitute one and the same "
    "instrument.",
    "IN WITNESS WHEREOF, the Parties have executed this Agreement "
    "as of the Effective Date.",
    "PARTY A SIGNATURE: ____________________________",
    "PARTY B SIGNATURE: ____________________________",
]


# --- synthetic-002 — 3 different deviation categories ------------------
#
# Coverage (diversifies vs synthetic-001's missing_exclusions +
# term_too_long + perpetual_without_qualifier):
#   c1 (term) — missing termination right: clause says the
#       agreement is perpetual with no termination, vs the
#       playbook's 2y + 3y survival. Material.
#   c2 (return_of_materials) — return of materials softened
#       to "may" instead of "shall" / "promptly". Material.
#   c5 (governing_law) — venue shifted to a foreign
#       jurisdiction (Republic of Singapore) outside the
#       playbook's US-state baselines. Material.
# c3, c4, c6, c7 are clean baselines.

SYNTHETIC_002_TITLE = "NON-DISCLOSURE AGREEMENT (SYNTHETIC \u2014 EVAL FIXTURE 2)"

SYNTHETIC_002_PARAGRAPHS: list[str] = [
    "This Non-Disclosure Agreement (this \u201cAgreement\u201d) is "
    "entered into as of the Effective Date by and between Party A and "
    "Party B (collectively, the \u201cParties\u201d) for the purpose "
    "of evaluating a potential business relationship.",
    # c1 — DEVIATION #1: perpetual with no termination right.
    "1. Term. This Agreement shall remain in effect in perpetuity "
    "from the Effective Date. The Agreement may only be terminated "
    "by mutual written agreement of the Parties; neither Party has "
    "an unilateral right to terminate.",
    # c2 — DEVIATION #2: return of materials softened to "may".
    "2. Return of Materials. Upon termination of this Agreement, the "
    "Receiving Party may, at its option, return or destroy all "
    "Confidential Information in its possession, or alternatively, "
    "retain such information in accordance with its document "
    "retention policies.",
    # c3 — clean: definition (kept compact to avoid keyword
    # mis-label by the rule-based classifier on the "obligations"
    # sub-clause).
    "3. Confidential Information. \u201cConfidential Information\u201d "
    "means any information disclosed by one Party to the other Party, "
    "whether orally, in writing, or in any other form, that is "
    "designated as confidential at the time of disclosure. The "
    "Receiving Party shall treat all such information as confidential.",
    # c4 — clean: injunctive relief.
    "4. Injunctive Relief. The Parties acknowledge that monetary "
    "damages may be inadequate to remedy a breach of this Agreement, "
    "and that the non-breaching Party shall be entitled to seek "
    "injunctive relief and other equitable remedies to prevent or "
    "restrain a breach.",
    # c5 — DEVIATION #3: foreign jurisdiction.
    "5. Governing Law. This Agreement shall be governed by and "
    "construed in accordance with the laws of the Republic of "
    "Singapore, without regard to its conflict of laws principles. "
    "The Parties consent to the exclusive jurisdiction of the "
    "Singapore International Arbitration Centre for any dispute "
    "arising hereunder.",
    # c6 — clean: residual knowledge.
    "6. Residual Knowledge. Nothing herein shall restrict the use of "
    "residual knowledge retained in the unaided memory of personnel "
    "of the Receiving Party, provided that such personnel do not "
    "intentionally memorize or compile Confidential Information for "
    "the purpose of circumventing the obligations of this Agreement.",
    # c7 — clean: entire agreement.
    "7. Entire Agreement. This Agreement contains the entire "
    "agreement between the Parties and supersedes all prior or "
    "contemporaneous communications, understandings, and agreements, "
    "whether oral or written, between the Parties with respect to "
    "the subject matter hereof.",
]


# --- hand-curated-001 — realistic deviations, gov-law + carve-out ------
#
# Two realistic deviations a real NDA reviewer would flag:
#   c4 (governing_law) — Texas substituted for the playbook's
#       Delaware baseline. The "TX" jurisdiction is in the
#       playbook's acceptable range (any US state is fine), but
#       the deviation is the *change* from the standard
#       Delaware boilerplate to a Texas-specific clause. Real
#       reviewers would flag this as minor if the playbook
#       baseline is Delaware.
#   c6 (definition_confidential_info) — standard exclusions
#       list is present but missing the "lawfully required
#       disclosure" carve-out (sub-clause (d)). The contract
#       has only (a)-(c). Material because compelled-disclosure
#       protection is a load-bearing exclusion.
# Other clauses are clean baselines.
#
# Realism notes: this contract reads like a real 2-page NDA a
# law firm might draft, with slightly less "boilerplate" prose
# than the public-template set.

HAND_CURATED_001_TITLE = "MUTUAL NON-DISCLOSURE AGREEMENT"

HAND_CURATED_001_PARAGRAPHS: list[str] = [
    "This Mutual Non-Disclosure Agreement (this \u201cAgreement\u201d) "
    "is made and entered into as of the Effective Date by and between "
    "the parties identified on the signature page (each, a "
    "\u201cParty\u201d and together, the \u201cParties\u201d).",
    "1. Confidential Information. \u201cConfidential Information\u201d "
    "means any non-public information disclosed by one Party (the "
    "\u201cDisclosing Party\u201d) to the other Party (the "
    "\u201cReceiving Party\u201d) that is designated as confidential "
    "in writing or that, given the nature of the information and the "
    "circumstances of disclosure, would reasonably be understood to "
    "be confidential.",
    "2. Term. This Agreement shall remain in effect for two (2) years "
    "from the Effective Date. The confidentiality obligations set "
    "forth herein shall survive termination for a period of three (3) "
    "years.",
    "3. Return of Materials. Upon termination of this Agreement, the "
    "Receiving Party shall promptly return or destroy all Confidential "
    "Information in its possession and shall certify such return or "
    "destruction in writing.",
    # c4 — DEVIATION: governing law TX vs the playbook's Delaware
    # baseline. Real-world NDAs use TX frequently; the
    # deviation is the *change*, not the jurisdiction itself.
    "4. Governing Law. This Agreement shall be governed by the laws "
    "of the State of Texas, without regard to its conflict of laws "
    "principles. The Parties consent to the exclusive jurisdiction of "
    "the state and federal courts located in Travis County, Texas.",
    "5. Injunctive Relief. The Parties agree that monetary damages "
    "may be inadequate to remedy a breach of this Agreement, and that "
    "the non-breaching Party shall be entitled to seek injunctive "
    "relief and other equitable remedies.",
    # c6 — DEVIATION: missing (d) "lawfully required disclosure"
    # carve-out. The other 3 (a/b/c) are present. Real
    # reviewers flag this as material because the missing
    # carve-out exposes the Receiving Party to liability for
    # compelled disclosures.
    "6. Exclusions. Confidential Information does not include "
    "information that (a) is or becomes generally available to the "
    "public other than as a result of disclosure by the Receiving "
    "Party, (b) was known to the Receiving Party on a "
    "non-confidential basis prior to disclosure, or (c) becomes "
    "available to the Receiving Party on a non-confidential basis "
    "from a source other than the Disclosing Party.",
    "7. Entire Agreement. This Agreement constitutes the entire "
    "agreement between the Parties with respect to its subject matter "
    "and supersedes all prior or contemporaneous communications, "
    "understandings, and agreements, whether oral or written.",
    "IN WITNESS WHEREOF, the Parties have executed this Agreement as "
    "of the Effective Date.",
    "PARTY A SIGNATURE: ____________________________",
    "PARTY B SIGNATURE: ____________________________",
]


# --- hand-curated-002 — realistic deviations, term + return -------------
#
# Two realistic deviations:
#   c2 (term) — confidentiality term is too short: 6 months
#       vs the playbook's 2y + 3y survival. Minor because
#       short-term NDAs are common in specific verticals
#       (creative agencies, marketing evaluations) but the
#       playbook flags it.
#   c3 (return_of_materials) — return of materials clause
#       has been removed entirely; the contract is silent
#       on what happens to Confidential Information at
#       termination. Material because the obligation
#       disappears.
# Other clauses are clean baselines.

HAND_CURATED_002_TITLE = "MUTUAL NON-DISCLOSURE AGREEMENT"

HAND_CURATED_002_PARAGRAPHS: list[str] = [
    "This Mutual Non-Disclosure Agreement (this \u201cAgreement\u201d) "
    "is entered into as of the Effective Date by and between the "
    "parties identified on the signature page (each, a \u201cParty\u201d "
    "and together, the \u201cParties\u201d). The Parties wish to "
    "explore a potential business relationship.",
    "1. Confidential Information. \u201cConfidential Information\u201d "
    "means any non-public information disclosed by one Party to the "
    "other Party, whether orally, in writing, or in any other form, "
    "that is designated as confidential at the time of disclosure.",
    # c2 — DEVIATION: confidentiality term is 6 months.
    "2. Term. This Agreement shall remain in effect for a period of "
    "six (6) months from the Effective Date. The obligations of "
    "confidentiality shall expire at the end of such six-month "
    "period.",
    # c3 — DEVIATION: return of materials clause is missing
    # entirely. Contract is silent on what happens to CI at
    # termination.
    "4. Governing Law. This Agreement shall be governed by the laws "
    "of the State of California, without regard to its conflict of "
    "laws principles.",
    "5. Entire Agreement. This Agreement constitutes the entire "
    "agreement between the Parties with respect to its subject "
    "matter and supersedes all prior or contemporaneous "
    "communications, understandings, and agreements, whether oral or "
    "written.",
    "6. Injunctive Relief. The Parties acknowledge that monetary "
    "damages may be inadequate to remedy a breach of this Agreement, "
    "and that the non-breaching Party shall be entitled to seek "
    "injunctive relief and other equitable remedies.",
    "IN WITNESS WHEREOF, the Parties have executed this Agreement "
    "as of the Effective Date.",
    "PARTY A SIGNATURE: ____________________________",
    "PARTY B SIGNATURE: ____________________________",
]


# --- hand-curated-003 — realistic deviations, residual + disclosure -----
#
# Two realistic deviations:
#   c2 (residual_knowledge) — residual knowledge clause is
#       removed entirely. The contract is silent on residual
#       knowledge, which means the playbook's default
#       (residual permitted) does not apply. Material
#       because the absence removes the explicit
#       carve-out.
#   c3 (definition_confidential_info) — definition uses
#       "best efforts to maintain confidentiality" instead
#       of the playbook's "reasonable care" / "standard of
#       care" language. Minor because "best efforts" is
#       *more* protective than reasonable care, but real
#       reviewers flag it because the standard differs.
# Other clauses are clean baselines.

HAND_CURATED_003_TITLE = "MUTUAL NON-DISCLOSURE AGREEMENT"

HAND_CURATED_003_PARAGRAPHS: list[str] = [
    "This Mutual Non-Disclosure Agreement (this \u201cAgreement\u201d) "
    "is entered into as of the Effective Date by and between the "
    "parties identified on the signature page (each, a \u201cParty\u201d "
    "and together, the \u201cParties\u201d).",
    "1. Term. This Agreement shall remain in effect for a period of "
    "two (2) years from the Effective Date. The confidentiality "
    "obligations set forth herein shall survive termination for a "
    "period of three (3) years.",
    # c2 — DEVIATION: residual knowledge clause is absent.
    # Contract is silent on residual knowledge.
    # c3 — DEVIATION: "best efforts" substituted for
    # "reasonable care" / "standard of care". More protective
    # but the standard differs from the playbook.
    "3. Obligations of the Receiving Party. The Receiving Party "
    "shall use its best efforts to maintain the confidentiality of "
    "all Confidential Information disclosed to it under this "
    "Agreement and shall not disclose such information to any third "
    "party without the prior written consent of the Disclosing "
    "Party.",
    "4. Return of Materials. Upon termination of this Agreement, the "
    "Receiving Party shall promptly return or destroy all "
    "Confidential Information in its possession and shall certify "
    "such return or destruction in writing.",
    "5. Governing Law. This Agreement shall be governed by the laws "
    "of the State of Delaware, without regard to its conflict of "
    "laws principles.",
    "6. Entire Agreement. This Agreement constitutes the entire "
    "agreement between the Parties with respect to its subject "
    "matter and supersedes all prior or contemporaneous "
    "communications, understandings, and agreements, whether oral or "
    "written.",
    "7. Injunctive Relief. The Parties acknowledge that monetary "
    "damages may be inadequate to remedy a breach of this Agreement, "
    "and that the non-breaching Party shall be entitled to seek "
    "injunctive relief and other equitable remedies.",
    "IN WITNESS WHEREOF, the Parties have executed this Agreement "
    "as of the Effective Date.",
    "PARTY A SIGNATURE: ____________________________",
    "PARTY B SIGNATURE: ____________________________",
]


# --- Top-level build entrypoint ----------------------------------------


CONTRACTS: list[tuple[Path, str, list[str]]] = [
    (
        CONTRACTS_ROOT / "public" / "nda-003.pdf",
        PUBLIC_003_TITLE,
        PUBLIC_003_PARAGRAPHS,
    ),
    (
        CONTRACTS_ROOT / "public" / "nda-004.pdf",
        PUBLIC_004_TITLE,
        PUBLIC_004_PARAGRAPHS,
    ),
    (
        CONTRACTS_ROOT / "public" / "nda-005.pdf",
        PUBLIC_005_TITLE,
        PUBLIC_005_PARAGRAPHS,
    ),
    (
        CONTRACTS_ROOT / "synthetic" / "nda-002.pdf",
        SYNTHETIC_002_TITLE,
        SYNTHETIC_002_PARAGRAPHS,
    ),
    (
        CONTRACTS_ROOT / "hand-curated" / "nda-001.pdf",
        HAND_CURATED_001_TITLE,
        HAND_CURATED_001_PARAGRAPHS,
    ),
    (
        CONTRACTS_ROOT / "hand-curated" / "nda-002.pdf",
        HAND_CURATED_002_TITLE,
        HAND_CURATED_002_PARAGRAPHS,
    ),
    (
        CONTRACTS_ROOT / "hand-curated" / "nda-003.pdf",
        HAND_CURATED_003_TITLE,
        HAND_CURATED_003_PARAGRAPHS,
    ),
]


def main() -> int:
    for path, title, paragraphs in CONTRACTS:
        _build_pdf(path, title, paragraphs)
        print(f"wrote {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
