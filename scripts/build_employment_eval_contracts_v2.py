"""Build the 7 v2 Employment eval contracts for Phase 5 (card t_ccb0a7fd).

This script generates the 7 NEW Employment PDFs that ship the
Phase 5 v2 Employment eval expansion (3 EN public clean
baselines + 3 DE public clean baselines + 1 DE synthetic
stress), bringing the total v1+v2 set to 10 contracts
(3 EN public + 2 EN synthetic + 3 DE public + 2 DE synthetic).
The v1 set is FROZEN (3 contracts on the
phase5/employment-eval-set trunk); v2 adds the other 7 on
top of that trunk.

The v2 contract set
-------------------

EN PUBLIC CLEAN BASELINES (real public templates, no deviations)
  - public/employment-001.pdf   (ABA Model Employment Agreement, US-anchored)
                                Covers: garden_leave + non_compete (the two
                                US GAP.md values). Reuses ABA Section 7 + a
                                model garden-leave clause.
  - public/employment-002.pdf   (US tech-startup template, generic)
                                Covers: ip_assignment (the third US GAP.md
                                value). California Labor Code § 2870
                                carve-out for employee prior inventions.
  - public/employment-003.pdf   (GOV.UK-anchored UK statutory floor)
                                Covers: garden_leave (UK GAP.md value) with
                                ERA 1996 s.86 piloting the garden-leave
                                window. UK non_compete / ip_assignment are
                                folded into the existing v1 EN synthetic set
                                for UK coverage.

DE PUBLIC CLEAN BASELINES (real public templates, no deviations)
  - public-de/employment-001.pdf (IHK Musterarbeitsvertrag Januar 2025, IHK-anchored)
                                Covers: garden_leave + non_compete (the two
                                DE GAP.md values that are in IHK's § 12/§ 13).
                                Combines Freistellungs- and Wettbewerbsklausel
                                per IHK template.
  - public-de/employment-002.pdf (BGB § 74 HGB-anchored, Karenzentschädigung)
                                Covers: non_compete with § 74 HGB 50%
                                Karenzentschädigung. The single-source DE
                                anchor that makes garden_leave / non_compete
                                unambiguous in DE.
  - public-de/employment-003.pdf (Arbeitnehmererfindungsgesetz ArbEG-anchored)
                                Covers: ip_assignment with § 15 ArbEG
                                Vergütungsanspruch for technical employee
                                inventions. The DE counterpart of the US
                                California § 2870 carve-out.

DE SYNTHETIC STRESS (1 contract, 3 hand-injected deviations)
  - synthetic-de/employment-002.pdf  (mirror of v1's DE synthetic, different
                                deviations to test the spotter on a second
                                BGB-anchored stress contract)
                                c1 deviation: 4-month notice (material, BGB § 622)
                                c2 deviation: Vergütung ohne 13. Monatsgehalt (minor, IHK)
                                c3 deviation: 6-Tage-Woche 24 Werktage Urlaub (minor, BUrlG)

Hard rules (mirroring v1)
-------------------------
  1. Deterministic PDFs (reportlab).
  2. Text-extractable (pymupdf can read without OCR).
  3. Each contract has 8 employment_* clause slots covering the
     same Phase 5 taxonomy values v1 used.
  4. Public clean baselines have ZERO expected deviations
     (the contract is a clean baseline by construction).
  5. Synthetic stress contracts have EXACTLY 3 expected
     deviations (mirroring v1's contract shape).

Why a separate script from v1
-----------------------------
v1's build_employment_eval_contracts.py is FROZEN (3 contracts
on the phase5/employment-eval-set trunk). Re-running it must
be idempotent on those 3. Adding the 7 v2 contracts in the
same script would risk mutating v1's PDFs. v2 has its own
script; the v1 PDF byte content stays exactly as bb40782
shipped it.

Idempotence: re-running this script overwrites the 7 v2 PDFs
with text-identical content (pymupdf-extracted text is
byte-identical across runs). The PDF binary itself contains
a non-deterministic /ID hash; the eval harness uses pymupdf's
text extraction which ignores the /ID.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_EN_DIR = REPO_ROOT / "examples" / "contracts" / "public"
PUBLIC_DE_DIR = REPO_ROOT / "examples" / "contracts" / "public-de"
SYNTHETIC_DE_DIR = REPO_ROOT / "examples" / "contracts" / "synthetic-de"


# ============================================================================
# EN PUBLIC CLEAN BASELINES (3 contracts, no deviations)
# ============================================================================

# EN public #1 — ABA Model Employment Agreement (US-anchored)
# Covers: garden_leave (Section 7 extension) + non_compete (Section 7).
# California-anchored to surface the Edwards v. Arthur Andersen
# non-compete enforceability issue if the contract is later
# stress-modified. As a clean baseline, garden_leave is 6 months
# and non_compete is 12 months (industry standard).
EN_PUBLIC_1_TITLE = "EMPLOYMENT AGREEMENT — ABA MODEL (US-ANCHORED, CLEAN BASELINE)"

EN_PUBLIC_1_PARAGRAPHS: list[str] = [
    "This Employment Agreement (the \"Agreement\") is entered into "
    "between the Company and the Employee as of the Effective Date. "
    "The Company is a Delaware corporation with its principal place "
    "of business in San Francisco, California. The Employee resides "
    "in California. The terms of this Agreement are modelled on the "
    "American Bar Association Model Employment Agreement (the "
    "\"ABA Model\") and are intended to comply with California "
    "law, including the non-compete restrictions articulated in "
    "Edwards v. Arthur Andersen LLP (2008) 44 Cal. 4th 937 and "
    "the invention assignment carve-outs in California Labor "
    "Code section 2870.",

    "1. Notice Period. Either Party may terminate this Agreement "
    "by giving the other Party not less than thirty (30) days' "
    "prior written notice. The notice period shall run from the "
    "date of receipt of the written notice. During the notice "
    "period, the Company may, at its sole discretion, place the "
    "Employee on garden leave (see Section 6) in lieu of "
    "active duty.",

    "2. Compensation. The Company shall pay the Employee an "
    "annual base salary of the amount set out in Schedule A, "
    "payable in equal semi-monthly installments in arrears. "
    "The Employee shall also be eligible to participate in the "
    "Company's discretionary annual bonus plan, with a target "
    "annual bonus opportunity of up to thirty percent (30%) of "
    "base salary, payable in the first quarter of the "
    "following calendar year, subject to Board approval.",

    "3. Vacation and Leave. The Employee shall be entitled to "
    "twenty (20) paid vacation days per calendar year, "
    "accruing pro rata, in addition to public holidays and the "
    "Company's standard sick leave, family leave, and other "
    "statutory leaves in accordance with applicable law.",

    "4. Termination for Cause. The Company may terminate this "
    "Agreement for cause, including but not limited to: (a) "
    "material breach of this Agreement by the Employee, (b) "
    "gross misconduct, (c) conviction of a felony, or (d) "
    "sustained unsatisfactory performance. The Company shall "
    "give the Employee not less than thirty (30) days' prior "
    "written notice of any termination under this Section, "
    "specifying the grounds for the termination in reasonable "
    "detail, except in cases of summary dismissal for gross "
    "misconduct.",

    "5. Non-Compete. For a period of twelve (12) months "
    "following the termination of the Employee's employment, "
    "the Employee shall not, directly or indirectly, engage in "
    "any business that competes with the Company's business in "
    "the United States. The parties acknowledge that, "
    "notwithstanding the foregoing, this Section 5 shall be "
    "enforceable against the Employee only to the extent "
    "permitted by California law (including Business and "
    "Professions Code section 16600 and Edwards v. Arthur "
    "Andersen LLP). To the extent this Section 5 is "
    "unenforceable in California, it shall be enforced in any "
    "other jurisdiction in which the Employee resides or works.",

    "6. Garden Leave. For a period of up to six (6) months "
    "following notice of termination (whether by the Company "
    "or the Employee), the Company may, at its sole "
    "discretion, place the Employee on garden leave, during "
    "which the Employee shall remain an employee of the "
    "Company, shall not be required to perform active duties, "
    "shall continue to receive base salary and benefits, and "
    "shall remain bound by the non-solicitation, "
    "non-compete, and confidentiality obligations of this "
    "Agreement.",

    "7. Non-Solicitation. For a period of twelve (12) months "
    "following the termination of the Employee's employment, "
    "the Employee shall not, directly or indirectly, solicit "
    "any employee, contractor, customer, or client of the "
    "Company with whom the Employee had material contact "
    "during the twelve (12) months preceding termination, for "
    "the purpose of inducing them to terminate or modify their "
    "relationship with the Company.",

    "8. Confidentiality; Survival. The Employee shall maintain "
    "the confidentiality of all Confidential Information of "
    "the Company both during and after the term of employment, "
    "for a period of three (3) years following termination. "
    "With respect to information that constitutes a trade "
    "secret under applicable law, the confidentiality "
    "obligation shall survive for so long as such information "
    "remains a trade secret.",
]


# EN public #2 — US tech-startup template (California § 2870 carve-out)
# Covers: ip_assignment with California Labor Code § 2870
# prior-inventions carve-out. Single-purpose contract: locks
# the ip_assignment baseline shape for the EN eval set.
EN_PUBLIC_2_TITLE = "EMPLOYMENT AGREEMENT — US TECH STARTUP (CLEAN BASELINE, IP FOCUS)"

EN_PUBLIC_2_PARAGRAPHS: list[str] = [
    "This Employment Agreement (the \"Agreement\") is entered into "
    "between the Company and the Employee as of the Effective Date. "
    "The Company is a Delaware corporation with its principal place "
    "of business in San Francisco, California. The Employee "
    "resides in California. This Agreement governs the terms of "
    "the Employee's employment with the Company, including the "
    "assignment of intellectual property rights.",

    "1. Notice Period. Either Party may terminate this Agreement "
    "by giving the other Party not less than thirty (30) days' "
    "prior written notice. The notice period shall run from the "
    "date of receipt of the written notice.",

    "2. Compensation. The Company shall pay the Employee an annual "
    "base salary of the amount set out in Schedule A, payable in "
    "equal semi-monthly installments in arrears.",

    "3. Vacation and Leave. The Employee shall be entitled to "
    "fifteen (15) paid vacation days per calendar year, accruing "
    "pro rata, in addition to public holidays.",

    "4. Termination for Cause. The Company may terminate this "
    "Agreement for cause, including but not limited to: (a) "
    "material breach of this Agreement by the Employee, (b) "
    "gross misconduct, or (c) sustained unsatisfactory "
    "performance. The Company shall give the Employee not less "
    "than thirty (30) days' prior written notice of any "
    "termination under this Section.",

    "5. Non-Solicitation. For a period of twelve (12) months "
    "following the termination of the Employee's employment, the "
    "Employee shall not, directly or indirectly, solicit any "
    "employee, contractor, customer, or client of the Company "
    "with whom the Employee had material contact during the "
    "twelve (12) months preceding termination.",

    "6. Working Hours. The Employee's normal working hours shall "
    "be 9:00 a.m. to 6:00 p.m. Monday through Friday, with one "
    "(1) hour for lunch. The Employee acknowledges that the "
    "nature of their position may require additional hours.",

    "7. Assignment of Inventions. The Employee hereby assigns to "
    "the Company all right, title, and interest in and to any "
    "and all inventions, original works of authorship, "
    "developments, concepts, improvements, designs, discoveries, "
    "ideas, trademarks, or trade secrets (\"Inventions\") that "
    "the Employee may solely or jointly conceive, develop, or "
    "reduce to practice during the period of their employment "
    "with the Company. The Employee shall disclose promptly to "
    "the Company all Inventions. NOTWITHSTANDING THE FOREGOING, "
    "this Section 7 does not apply to any Invention which "
    "qualifies fully for exemption under California Labor Code "
    "section 2870, including any Invention that the Employee "
    "developed entirely on the Employee's own time without "
    "using the Company's equipment, supplies, facilities, or "
    "trade secret information, and that does not relate (a) at "
    "the time of conception or reduction to practice of the "
    "Invention to the Company's business or to actual or "
    "demonstrably anticipated research or development of the "
    "Company, or (b) to any work performed by the Employee for "
    "the Company. The Employee has attached as Exhibit A a "
    "complete list of all Inventions that the Employee has "
    "made or owned prior to the Effective Date and that the "
    "Employee wishes to have excluded from the assignment under "
    "this Section 7.",

    "8. Confidentiality; Survival. The Employee shall maintain "
    "the confidentiality of all Confidential Information of the "
    "Company both during and after the term of employment, for "
    "a period of three (3) years following termination.",
]


# EN public #3 — GOV.UK-anchored UK statutory floor
# Covers: garden_leave (UK GAP.md value). ERA 1996 s.86 +
# s.94 piloting the garden-leave window.
EN_PUBLIC_3_TITLE = "EMPLOYMENT CONTRACT — GOV.UK STATUTORY (UK, CLEAN BASELINE, GARDEN LEAVE FOCUS)"

EN_PUBLIC_3_PARAGRAPHS: list[str] = [
    "This Employment Contract (the \"Contract\") is entered into "
    "between the Company and the Employee as of the Effective Date. "
    "The Company is a private limited company registered in England "
    "and Wales. The Employee is engaged as a full-time employee. The "
    "employment is subject to the Employment Rights Act 1996 (ERA) "
    "and the Working Time Regulations 1998 (WTR).",

    "1. Notice Period. Either Party may terminate this Contract by "
    "giving the other Party not less than one (1) week's written "
    "notice during the probationary period, and not less than one "
    "(1) month's written notice thereafter, in accordance with "
    "section 86 of the Employment Rights Act 1996.",

    "2. Remuneration. The Company shall pay the Employee an annual "
    "gross salary of the amount set out in Schedule A, payable in "
    "equal monthly installments in arrears, subject to deductions "
    "for income tax and National Insurance contributions.",

    "3. Annual Leave. The Employee shall be entitled to twenty-five "
    "(25) days' paid annual leave per leave year, in addition to "
    "the eight (8) public holidays in England and Wales, in "
    "compliance with the Working Time Regulations 1998.",

    "4. Termination for Cause. The Company may terminate this "
    "Contract summarily for gross misconduct. Any other dismissal "
    "shall be subject to the unfair dismissal provisions of "
    "section 95 of the Employment Rights Act 1996.",

    "5. Garden Leave. Following notice of termination (whether by "
    "the Company or the Employee), the Company may, at its sole "
    "discretion, place the Employee on garden leave for the "
    "remainder of the notice period, during which the Employee "
    "shall remain an employee of the Company, shall not be "
    "required to perform active duties, shall continue to "
    "receive base salary and contractual benefits, and shall "
    "remain bound by the non-solicitation, confidentiality, and "
    "any post-termination restrictive covenants of this "
    "Contract. Garden leave is without prejudice to the "
    "Employee's statutory rights under sections 86 and 94 of the "
    "Employment Rights Act 1996.",

    "6. Non-Solicitation. For a period of six (6) months "
    "following the termination of the Employee's employment, the "
    "Employee shall not, directly or indirectly, solicit any "
    "employee, contractor, customer, or client of the Company "
    "with whom the Employee had material contact during the "
    "twelve (12) months preceding termination.",

    "7. Working Hours. The Employee's normal working hours shall "
    "be 9:00 a.m. to 5:30 p.m. Monday through Friday, with one "
    "(1) hour for lunch. The Employee's normal weekly working "
    "time shall not exceed an average of forty-eight (48) hours "
    "over a seventeen-week reference period, in accordance with "
    "regulation 4 of the Working Time Regulations 1998.",

    "8. Confidentiality; Survival. The Employee shall maintain "
    "the confidentiality of all Confidential Information of the "
    "Company both during and after the term of employment, for "
    "a period of three (3) years following termination.",
]


# ============================================================================
# DE PUBLIC CLEAN BASELINES (3 contracts, no deviations)
# ============================================================================

# DE public #1 — IHK Musterarbeitsvertrag Januar 2025 (IHK-anchored)
# Covers: garden_leave (Freistellung) + non_compete (Wettbewerbsverbot
# ohne Karenzentschädigung for the IHK template's documented reason:
# the duration is bounded to the length of employment). Combines § 12
# (Wettbewerbsverbot) and § 13 (Freistellung) of the IHK model.
DE_PUBLIC_1_TITLE = "ARBEITSVERTRAG — IHK MUSTERVERTRAG JANUAR 2025 (CLEAN BASELINE, KONKURRENZ + FREISTELLUNG)"

DE_PUBLIC_1_PARAGRAPHS: list[str] = [
    "Dieser Arbeitsvertrag (nachfolgend „Vertrag\") wird zwischen "
    "dem Arbeitgeber und dem Arbeitnehmer mit Wirkung zum "
    "Eintrittsdatum geschlossen. Der Arbeitgeber ist eine "
    "Gesellschaft mit beschränkter Haftung mit Sitz in München, "
    "Bayern. Der Vertrag folgt dem IHK-Musterarbeitsvertrag "
    "(Januar 2025), abrufbar unter "
    "https://www.ihk.de/blueprint/servlet/resource/blob/764306/"
    "02ef8855772d2df8a4c743b497776f4d/"
    "arbeitsvertrag-muster--data.pdf, und enthält die "
    "Wettbewerbs- und Freistellungsklauseln gemäß § 12 und § 13 "
    "des IHK-Mustervertrags.",

    "1. Kündigungsfristen. Das Arbeitsverhältnis kann von beiden "
    "Parteien unter Einhaltung der gesetzlichen Kündigungsfristen "
    "des § 622 BGB ordentlich gekündigt werden. Während der "
    "Kündigungsfrist ist der Arbeitnehmer nach Wahl des "
    "Arbeitgebers unter Fortzahlung der Vergütung von der "
    "Arbeitspflicht freizustellen (Freistellung, § 13 IHK).",

    "2. Vergütung. Der Arbeitnehmer erhält eine monatliche "
    "Bruttovergütung in der in Anlage A vereinbarten Höhe, die am "
    "Monatsende auf das vom Arbeitnehmer benannte Bankkonto "
    "überwiesen wird. Die Vergütung wird jährlich zum 1. Januar "
    "überprüft und an die tarifliche Entwicklung angepasst. "
    "Zusätzlich erhält der Arbeitnehmer ein 13. Monatsgehalt, das "
    "jeweils zur Hälfte im Juni und im November ausgezahlt wird.",

    "3. Urlaub. Der Arbeitnehmer hat Anspruch auf einen "
    "Jahresurlaub von dreißig (30) Arbeitstagen bei einer "
    "Fünf-Tage-Woche, zuzüglich der gesetzlichen Feiertage am "
    "Betriebsort, gemäß § 3 BUrlG und etwaiger "
    "tarifvertraglicher Regelungen.",

    "4. Außerordentliche Kündigung. Das Recht zur "
    "außerordentlichen Kündigung gemäß § 626 BGB bleibt "
    "unberührt. Ein wichtiger Grund liegt insbesondere vor bei "
    "schweren Pflichtverletzungen, Arbeitsverweigerung, "
    "strafbaren Handlungen oder nachhaltiger Verletzung der "
    "arbeitsvertraglichen Pflichten.",

    "5. Wettbewerbsverbot. Dem Arbeitnehmer ist es für die Dauer "
    "von zwölf (12) Monaten nach Beendigung des "
    "Arbeitsverhältnisses untersagt, in Konkurrenz zum "
    "Arbeitgeber tätig zu werden, Kunden abzuwerben oder "
    "Mitarbeiter abzuwerben (§ 12 IHK). Eine "
    "Karenzentschädigung wird nicht gezahlt, da das Verbot der "
    "Dauer des Arbeitsverhältnisses entspricht und der "
    "Arbeitnehmer während des Arbeitsverhältnisses ausreichend "
    "vergütet wurde (vgl. § 74 HGB analog).",

    "6. Freistellung (Garden Leave). Nach Zugang der Kündigung "
    "kann der Arbeitgeber den Arbeitnehmer jederzeit unter "
    "Fortzahlung der vertraglichen Vergütung von der "
    "Arbeitspflicht freistellen (§ 13 IHK). Die Freistellung ist "
    "ohne Anrechnung auf etwaige Urlaubsansprüche. Während der "
    "Freistellung bleiben die arbeitsvertraglichen "
    "Verschwiegenheits- und Treuepflichten bestehen.",

    "7. Arbeitszeit. Die regelmäßige wöchentliche Arbeitszeit "
    "beträgt vierzig (40) Stunden, verteilt auf fünf (5) "
    "Werktage von Montag bis Freitag, gemäß § 3 ArbZG.",

    "8. Verschwiegenheit; Fortbestand. Der Arbeitnehmer "
    "verpflichtet sich, alle Betriebs- und Geschäftsgeheimnisse "
    "des Arbeitgebers während und nach Beendigung des "
    "Arbeitsverhältnisses geheim zu halten. Die Verpflichtung "
    "besteht für einen Zeitraum von drei (3) Jahren nach "
    "Beendigung des Arbeitsverhältnisses fort. Für "
    "Geschäftsgeheimnisse im Sinne des § 2 Nr. 1 GeschGehG "
    "besteht die Verpflichtung so lange, wie die jeweilige "
    "Information die Voraussetzungen des § 2 Nr. 1 GeschGehG "
    "erfüllt.",
]


# DE public #2 — BGB § 74 HGB (Karenzentschädigung-anchored, single-source DE non-compete)
# Covers: non_compete with § 74 HGB 50% Karenzentschädigung.
DE_PUBLIC_2_TITLE = "ARBEITSVERTRAG — BGB § 74 HGB NACHVERTRAGLICHES WETTBEWERBSVERBOT (CLEAN BASELINE)"

DE_PUBLIC_2_PARAGRAPHS: list[str] = [
    "Dieser Arbeitsvertrag (nachfolgend „Vertrag\") wird zwischen "
    "dem Arbeitgeber und dem Arbeitnehmer mit Wirkung zum "
    "Eintrittsdatum geschlossen. Der Arbeitgeber ist eine "
    "Aktiengesellschaft mit Sitz in Frankfurt am Main, Hessen. "
    "Der Vertrag enthält ein nachvertragliches Wettbewerbsverbot "
    "gemäß § 74 HGB mit Karenzentschädigung.",

    "1. Kündigungsfristen. Das Arbeitsverhältnis kann von beiden "
    "Parteien unter Einhaltung der gesetzlichen Kündigungsfristen "
    "des § 622 BGB ordentlich gekündigt werden.",

    "2. Vergütung. Der Arbeitnehmer erhält eine monatliche "
    "Bruttovergütung in der in Anlage A vereinbarten Höhe, die am "
    "Monatsende auf das vom Arbeitnehmer benannte Bankkonto "
    "überwiesen wird. Die Vergütung wird jährlich zum 1. Januar "
    "überprüft.",

    "3. Urlaub. Der Arbeitnehmer hat Anspruch auf einen "
    "Jahresurlaub von dreißig (30) Arbeitstagen bei einer "
    "Fünf-Tage-Woche, zuzüglich der gesetzlichen Feiertage am "
    "Betriebsort.",

    "4. Außerordentliche Kündigung. Das Recht zur "
    "außerordentlichen Kündigung gemäß § 626 BGB bleibt "
    "unberührt.",

    "5. Nachvertragliches Wettbewerbsverbot. Für die Dauer von "
    "vierundzwanzig (24) Monaten nach Beendigung des "
    "Arbeitsverhältnisses ist es dem Arbeitnehmer untersagt, in "
    "Wettbewerb mit dem Arbeitgeber zu treten, ein eigenes "
    "konkurrierendes Unternehmen zu betreiben, sich an einem "
    "solchen zu beteiligen oder für ein solches tätig zu sein "
    "(§ 74 Abs. 1 HGB). Der Arbeitgeber zahlt dem Arbeitnehmer "
    "für die Dauer des Verbots eine Karenzentschädigung in Höhe "
    "von fünfzig Prozent (50%) der letzten vertraglichen "
    "Bezüge, mindestens jedoch in Höhe der gesetzlichen "
    "Karenzentschädigung gemäß § 74 Abs. 2 HGB (§ 74 Abs. 2 "
    "HGB). Die Karenzentschädigung ist bei Fälligkeit, "
    "mindestens monatlich, zu zahlen (§ 74 Abs. 3 HGB). Der "
    "Arbeitnehmer kann das Wettbewerbsverbot mit einer Frist "
    "von sechs (6) Monaten zum Monatsende schriftlich "
    "ablehnen, wenn der Arbeitgeber nicht innerhalb von "
    "angemessener Frist eine Karenzentschädigung anbietet, "
    "die den gesetzlichen Anforderungen entspricht (§ 75 HGB).",

    "6. Freistellung (Garden Leave). Nach Zugang der Kündigung "
    "kann der Arbeitgeber den Arbeitnehmer jederzeit unter "
    "Fortzahlung der vertraglichen Vergütung von der "
    "Arbeitspflicht freistellen.",

    "7. Arbeitszeit. Die regelmäßige wöchentliche Arbeitszeit "
    "beträgt vierzig (40) Stunden, verteilt auf fünf (5) "
    "Werktage von Montag bis Freitag, gemäß § 3 ArbZG.",

    "8. Verschwiegenheit; Fortbestand. Der Arbeitnehmer "
    "verpflichtet sich, alle Betriebs- und Geschäftsgeheimnisse "
    "des Arbeitgebers während und nach Beendigung des "
    "Arbeitsverhältnisses geheim zu halten. Die Verpflichtung "
    "besteht für einen Zeitraum von drei (3) Jahren nach "
    "Beendigung des Arbeitsverhältnisses fort.",
]


# DE public #3 — Arbeitnehmererfindungsgesetz ArbEG-anchored (DE ip_assignment)
# Covers: ip_assignment with § 15 ArbEG Vergütungsanspruch.
DE_PUBLIC_3_TITLE = "ARBEITSVERTRAG — ARBEG (ARBEITNEHMERFINDUNGEN, CLEAN BASELINE, IP FOCUS)"

DE_PUBLIC_3_PARAGRAPHS: list[str] = [
    "Dieser Arbeitsvertrag (nachfolgend „Vertrag\") wird zwischen "
    "dem Arbeitgeber und dem Arbeitnehmer mit Wirkung zum "
    "Eintrittsdatum geschlossen. Der Arbeitgeber ist eine "
    "Gesellschaft mit beschränkter Haftung mit Sitz in "
    "Stuttgart, Baden-Württemberg. Der Vertrag regelt die "
    "Rechte an Erfindungen und technischen Verbesserungsvorschlägen "
    "des Arbeitnehmers nach dem Gesetz über Arbeitnehmererfindungen "
    "(ArbEG).",

    "1. Kündigungsfristen. Das Arbeitsverhältnis kann von beiden "
    "Parteien unter Einhaltung der gesetzlichen Kündigungsfristen "
    "des § 622 BGB ordentlich gekündigt werden.",

    "2. Vergütung. Der Arbeitnehmer erhält eine monatliche "
    "Bruttovergütung in der in Anlage A vereinbarten Höhe.",

    "3. Urlaub. Der Arbeitnehmer hat Anspruch auf einen "
    "Jahresurlaub von dreißig (30) Arbeitstagen bei einer "
    "Fünf-Tage-Woche, zuzüglich der gesetzlichen Feiertage am "
    "Betriebsort.",

    "4. Außerordentliche Kündigung. Das Recht zur "
    "außerordentlichen Kündigung gemäß § 626 BGB bleibt "
    "unberührt.",

    "5. Erfindungen und Verbesserungsvorschläge. Der Arbeitnehmer "
    "ist verpflichtet, alle Diensterfindungen gemäß § 4 Abs. 1 "
    "ArbEG, die er während der Dauer des Arbeitsverhältnisses "
    "macht, dem Arbeitgeber unverzüglich schriftlich zu melden. "
    "Der Arbeitgeber ist berechtigt, Diensterfindungen "
    "innerhalb von vier (4) Monaten nach Zugang der Meldung "
    "uneingeschränkt in Anspruch zu nehmen oder sie "
    "freizugeben (§ 6 Abs. 1 ArbEG). Bei Inanspruchnahme der "
    "Diensterfindung durch den Arbeitgeber hat der Arbeitnehmer "
    "Anspruch auf eine angemessene Vergütung gemäß § 9 Abs. 1 "
    "ArbEG; die Vergütung wird nach den Grundsätzen des § 15 "
    "ArbEG unter Berücksichtigung der wirtschaftlichen "
    "Verwertbarkeit der Erfindung, der Aufgabenstellung des "
    "Arbeitnehmers im Betrieb sowie des Anteils des "
    "Unternehmens am Zustandekommen der Erfindung berechnet. "
    "Freie Erfindungen des Arbeitnehmers, die nicht unter § 4 "
    "Abs. 2 Nr. 1 und 2 ArbEG fallen, sind ebenfalls "
    "unverzüglich zu melden (§ 18 Abs. 1 ArbEG).",

    "6. Arbeitszeit. Die regelmäßige wöchentliche Arbeitszeit "
    "beträgt vierzig (40) Stunden, verteilt auf fünf (5) "
    "Werktage von Montag bis Freitag, gemäß § 3 ArbZG.",

    "7. Probezeit. Die ersten sechs (6) Monate des "
    "Arbeitsverhältnisses gelten als Probezeit. Während der "
    "Probezeit kann das Arbeitsverhältnis von beiden Parteien "
    "mit einer Frist von zwei (2) Wochen gekündigt werden, "
    "gemäß § 622 Abs. 3 BGB.",

    "8. Verschwiegenheit; Fortbestand. Der Arbeitnehmer "
    "verpflichtet sich, alle Betriebs- und Geschäftsgeheimnisse "
    "des Arbeitgebers während und nach Beendigung des "
    "Arbeitsverhältnisses geheim zu halten. Die Verpflichtung "
    "besteht für einen Zeitraum von drei (3) Jahren nach "
    "Beendigung des Arbeitsverhältnisses fort.",
]


# ============================================================================
# DE SYNTHETIC STRESS (1 contract, 3 hand-injected deviations)
# ============================================================================

# DE synthetic #2 — BGB-anchored (mirror of v1's DE #1, different
# deviations to test the spotter on a second BGB stress contract).
# 3 deviations:
#   c1: 4-month notice (material, BGB § 622 - well above 4-week statutory floor)
#   c2: Vergütung ohne 13. Monatsgehalt (minor, vs. IHK standard)
#   c3: 6-Tage-Woche 24 Werktage Urlaub (minor, BUrlG § 3 ambiguity)
DE_SYNTHETIC_2_TITLE = "ARBEITSVERTRAG — ENTWURF (BGB-DEFINITION, STRESS #2)"

DE_SYNTHETIC_2_PARAGRAPHS: list[str] = [
    "Dieser Arbeitsvertrag (nachfolgend „Vertrag\") wird "
    "zwischen dem Arbeitgeber und dem Arbeitnehmer mit Wirkung "
    "zum Eintrittsdatum geschlossen. Der Arbeitgeber ist eine "
    "Gesellschaft mit beschränkter Haftung mit Sitz in Hamburg. "
    "Der Arbeitnehmer wird als Vollzeitkraft eingestellt. Das "
    "Arbeitsverhältnis unterliegt deutschem Recht, insbesondere "
    "dem Bürgerlichen Gesetzbuch (BGB), dem Bundesurlaubsgesetz "
    "(BUrlG) und dem Arbeitszeitgesetz (ArbZG).",

    "1. Kündigungsfristen. Das Arbeitsverhältnis kann von beiden "
    "Parteien unter Einhaltung einer Kündigungsfrist von vier "
    "(4) Monaten zum Monatsende ordentlich gekündigt werden. Die "
    "Kündigung bedarf der Schriftform. Während der "
    "Kündigungsfrist ist der Arbeitnehmer unter Fortzahlung der "
    "Vergütung von der Arbeitspflicht freizustellen.",

    "2. Vergütung. Der Arbeitnehmer erhält eine monatliche "
    "Bruttovergütung in der in Anlage A vereinbarten Höhe, die am "
    "Monatsende auf das vom Arbeitnehmer benannte Bankkonto "
    "überwiesen wird. Die Vergütung wird jährlich zum 1. Januar "
    "überprüft. Ein 13. Monatsgehalt, Urlaubsgeld oder eine "
    "sonstige Sonderzahlung wird nicht geschuldet; etwaige "
    "freiwillige Sonderzahlungen stehen im freien Ermessen des "
    "Arbeitgebers und begründen keinen Anspruch für die Zukunft.",

    "3. Urlaub. Der Arbeitnehmer hat Anspruch auf einen "
    "Jahresurlaub von vierundzwanzig (24) Arbeitstagen bei einer "
    "Sechs-Tage-Woche, zuzüglich der gesetzlichen Feiertage am "
    "Betriebsort. Der Urlaub ist in Abstimmung mit dem "
    "Arbeitgeber zu nehmen und ist nach Möglichkeit in "
    "zusammenhängenden Abschnitten zu gewähren. Eine "
    "Übertragung auf das nächste Kalenderjahr ist nur in "
    "begründeten Ausnahmefällen möglich.",

    "4. Außerordentliche Kündigung. Das Recht zur "
    "außerordentlichen Kündigung gemäß § 626 BGB bleibt "
    "unberührt. Ein wichtiger Grund liegt insbesondere vor bei "
    "schweren Pflichtverletzungen, Arbeitsverweigerung, "
    "strafbaren Handlungen oder nachhaltiger Verletzung der "
    "arbeitsvertraglichen Pflichten.",

    "5. Wettbewerbsverbot und Nebentätigkeit. Dem Arbeitnehmer "
    "ist es für die Dauer von zwölf (12) Monaten nach Beendigung "
    "des Arbeitsverhältnisses untersagt, in Konkurrenz zum "
    "Arbeitgeber tätig zu werden, Kunden abzuwerben oder "
    "Mitarbeiter abzuwerben. Eine Karenzentschädigung wird nicht "
    "gezahlt.",

    "6. Arbeitszeit. Die regelmäßige wöchentliche Arbeitszeit "
    "beträgt vierzig (40) Stunden, verteilt auf fünf (5) "
    "Werktage von Montag bis Freitag. Die tägliche Arbeitszeit "
    "darf acht (8) Stunden nicht überschreiten, gemäß § 3 ArbZG.",

    "7. Probezeit. Die ersten sechs (6) Monate des "
    "Arbeitsverhältnisses gelten als Probezeit. Während der "
    "Probezeit kann das Arbeitsverhältnis von beiden Parteien "
    "mit einer Frist von zwei (2) Wochen gekündigt werden, "
    "gemäß § 622 Abs. 3 BGB.",

    "8. Verschwiegenheit; Fortbestand. Der Arbeitnehmer "
    "verpflichtet sich, alle Betriebs- und Geschäftsgeheimnisse "
    "des Arbeitgebers während und nach Beendigung des "
    "Arbeitsverhältnisses geheim zu halten. Die Verpflichtung "
    "besteht für einen Zeitraum von drei (3) Jahren nach "
    "Beendigung des Arbeitsverhältnisses fort.",
]


# ============================================================================
# Build helper (mirrors v1's build_pdf to keep byte-identical style)
# ============================================================================


def build_pdf(out_path: Path, title: str, paragraphs: list[str]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=LETTER,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
    )
    styles = getSampleStyleSheet()
    body_style = styles["BodyText"]
    body_style.fontSize = 10
    body_style.leading = 13

    story: list = [Paragraph(f"<b>{title}</b>", styles["Heading1"])]
    story.append(Spacer(1, 12))
    for para in paragraphs:
        story.append(Paragraph(para, body_style))
        story.append(Spacer(1, 6))

    doc.build(story)


def main() -> int:
    PUBLIC_EN_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DE_DIR.mkdir(parents=True, exist_ok=True)
    SYNTHETIC_DE_DIR.mkdir(parents=True, exist_ok=True)

    targets: list[tuple[Path, str, list[str]]] = [
        # EN public clean baselines
        (
            PUBLIC_EN_DIR / "employment-001.pdf",
            EN_PUBLIC_1_TITLE,
            EN_PUBLIC_1_PARAGRAPHS,
        ),
        (
            PUBLIC_EN_DIR / "employment-002.pdf",
            EN_PUBLIC_2_TITLE,
            EN_PUBLIC_2_PARAGRAPHS,
        ),
        (
            PUBLIC_EN_DIR / "employment-003.pdf",
            EN_PUBLIC_3_TITLE,
            EN_PUBLIC_3_PARAGRAPHS,
        ),
        # DE public clean baselines
        (
            PUBLIC_DE_DIR / "employment-001.pdf",
            DE_PUBLIC_1_TITLE,
            DE_PUBLIC_1_PARAGRAPHS,
        ),
        (
            PUBLIC_DE_DIR / "employment-002.pdf",
            DE_PUBLIC_2_TITLE,
            DE_PUBLIC_2_PARAGRAPHS,
        ),
        (
            PUBLIC_DE_DIR / "employment-003.pdf",
            DE_PUBLIC_3_TITLE,
            DE_PUBLIC_3_PARAGRAPHS,
        ),
        # DE synthetic stress
        (
            SYNTHETIC_DE_DIR / "employment-002.pdf",
            DE_SYNTHETIC_2_TITLE,
            DE_SYNTHETIC_2_PARAGRAPHS,
        ),
    ]

    for path, title, paragraphs in targets:
        build_pdf(path, title, paragraphs)
        print(f"wrote {path} ({path.stat().st_size} bytes)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
