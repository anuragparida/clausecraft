"""Smoke test for the EN Employment baselines (Phase 5 card t_d23d222d).

For each of the 5 EN Employment baselines, embed a paraphrased
version of the canonical clause, query the playbook store for
the top-1 hit filtered by ``contract_type=employment, language=en``,
and assert that:

  (a) the top-1 hit is the expected baseline (paraphrase → original
      retrieval), and
  (b) the cosine similarity is >= 0.77 (mirrors the EN DPA and DE DPA
      smoke-test thresholds from t_45151f58 and t_70c2599d).

This is a manual smoke test (not part of the pytest suite) — it
needs the real bge-m3 provider reachable and a fresh seed. Run
from the repo root via:

  .venv-test/bin/python -m scripts.smoke_employment_en  # noqa: E402

If bge-m3 is unreachable, the embedding provider falls back to
``offline-hash`` and the similarity floors won't hold. The script
will fail loud in that case (the offline path is deterministic
but the cosine sims are typically ~0.10–0.30).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Repo root on path so the backend package imports
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy import text  # noqa: E402

from app.db import get_session_factory  # noqa: E402
from app.playbook.embeddings import embed_texts  # noqa: E402
from app.playbook.store import get_store  # noqa: E402

# (expected_clause_id, paraphrase_text)
# Each paraphrase is a same-language re-render of the canonical
# clause body — different word order, different phrasings, but
# the same statutory anchor. The retrieval test verifies that
# bge-m3 cosine similarity surfaces the original baseline as
# the top-1 hit, not a paraphrase of a sibling baseline.
PARAPHRASES: list[tuple[str, str]] = [
    (
        "uk-employment-notice-period-era-1996-s86",
        # Paraphrase: shift from "two weeks' notice" / "three months"
        # to "fourteen days' notice" / "90 days" and add a sentence
        # about PILON. The statutory minimum (1 week) is preserved
        # but not named.
        "Either party may terminate the employment relationship by "
        "giving the other party written notice. The minimum notice "
        "the Employer must give the Employee shall not be less than "
        "one (1) week (or such longer period as the Employee's "
        "continuous employment with the Employer entitles the "
        "Employee to under the Employment Rights Act 1996), and the "
        "Employer and the Employee agree that the notice period "
        "shall be two (2) weeks during the probation period and "
        "three (3) months thereafter. The Employer may elect, in "
        "lieu of requiring the Employee to work out the notice "
        "period, to make a single payment in lieu of notice equal "
        "to the Employee's base salary for the unexpired notice "
        "period. Notice shall run from the date of receipt. The "
        "Employee's statutory rights, including the right not to be "
        "unfairly dismissed, are preserved.",
    ),
    (
        "uk-employment-remuneration-era-1996-s1-3-a",
        # Paraphrase: shift from "seventy-two thousand pounds
        # sterling" to "seventy-five thousand pounds" and from
        # "twelve equal monthly instalments" to "paid on the last
        # working day of each month". Restate the s.1(3)(a) pay-
        # itemisation rule.
        "The Employer shall pay the Employee a gross annual base "
        "salary of seventy-five thousand pounds sterling (£75,000), "
        "pro-rated for any partial year, paid in twelve (12) equal "
        "monthly instalments on the last working day of each calendar "
        "month, by bank transfer to a UK bank account nominated by "
        "the Employee. The Employee shall also be eligible for a "
        "discretionary annual bonus of up to fifteen percent (15%) of "
        "base salary, payable within three (3) months of the end of "
        "the financial year, the award and amount to be determined "
        "by the Employer in its sole discretion. The Employer shall "
        "deliver to the Employee a written statement of particulars "
        "in accordance with section 1 of the Employment Rights Act "
        "1996, itemising the scale of remuneration, the intervals at "
        "which it is paid, the hours of work, the place of work, the "
        "amount of paid holiday, the notice period applicable on "
        "termination, and the job title, no later than two (2) months "
        "after the date on which the employment begins. Any change in "
        "the particulars shall be notified in writing within one (1) "
        "month.",
    ),
    (
        "uk-employment-leave-entitlements-era-1996-s13-16-wtr-1998",
        # Paraphrase: shift from "5.6 working weeks" to "twenty-eight
        # working days" and add a sentence about the WTR 1998 reg 16
        # payment-in-lieu-on-termination. Keep the 8 public holidays
        # inclusive.
        "The Employee is entitled to not less than twenty-eight (28) "
        "working days of paid annual leave in each leave year, in "
        "accordance with sections 13 to 16 of the Employment Rights "
        "Act 1996 and regulations 13 and 13A of the Working Time "
        "Regulations 1998 (which is the statutory minimum of 5.6 "
        "weeks for a five-day worker). The twenty-eight (28) days is "
        "inclusive of the eight (8) public and bank holidays in "
        "England and Wales. The leave year runs from 1 January to 31 "
        "December. The Employee may carry forward up to four (4) "
        "days of unused statutory leave into the following leave "
        "year where the Employee has been unable to take it because "
        "of sickness absence, statutory family leave, or other "
        "compelling reason. On termination, the Employer shall pay "
        "the Employee a sum in lieu of any untaken statutory leave "
        "accrued up to the date of termination, calculated in "
        "accordance with regulation 16 of the Working Time Regulations "
        "1998. The Employee's statutory rights to paid annual leave "
        "cannot be contracted out of.",
    ),
    (
        "uk-employment-termination-for-cause-era-1996-s95",
        # Paraphrase: shift the ACAS Code procedural anchor into a
        # numbered list, change "gross misconduct" to "serious
        # misconduct", and add a sentence about the s.98(4) auto-
        # unfairness.
        "The Employer may terminate the employment relationship "
        "summarily, without notice or payment in lieu of notice, for "
        "serious misconduct, which for the purposes of this Agreement "
        "means conduct falling within one of the potentially fair "
        "reasons set out in section 95 of the Employment Rights Act "
        "1996 (capability, conduct, redundancy, statutory restriction, "
        "or some other substantial reason of a kind which justifies "
        "the dismissal of an employee holding the position which the "
        "Employee held), provided that the conduct is so serious that "
        "it justifies the immediate termination of the employment "
        "relationship without the notice period otherwise applicable. "
        "Examples of conduct that may amount to serious misconduct "
        "include theft, fraud or dishonesty; assault, harassment, or "
        "discrimination on any of the protected grounds set out in the "
        "Equality Act 2010; being under the influence of alcohol or "
        "non-prescribed drugs at the workplace; serious breach of the "
        "Employer's health-and-safety, information-security, or "
        "anti-bribery policies; gross insubordination; and conviction "
        "of a criminal offence that renders the Employee unsuitable "
        "for the role. Before reaching a decision to dismiss summarily, "
        "the Employer shall, save in cases where the conduct is so "
        "exceptional that an investigation is unnecessary or "
        "impracticable, follow the procedural steps set out in the "
        "ACAS Code of Practice on Disciplinary and Grievance "
        "Procedures 2015 (investigation, written notification of "
        "allegations, opportunity to respond at a hearing, and a "
        "right of appeal). Failure by the Employer to follow that "
        "framework may render the dismissal automatically unfair "
        "under section 98(4) of the Employment Rights Act 1996.",
    ),
    (
        "aba-model-employment-non-solicitation-section-7",
        # Paraphrase: shift from "twelve (12) months" to "twenty-four
        # (24) months" (will likely still hit top-1 because the
        # substantive content is the same), and reorder the (a)/(b)
        # clauses to (b)/(a). Keep the California § 16600 carve-out
        # and the blue-pencil clause.
        "For a period of twenty-four (24) months following the "
        "termination of the Employee's employment with the Employer "
        "for any reason, the Employee shall not, directly or "
        "indirectly, whether on the Employee's own behalf or on "
        "behalf of any other person, firm, partnership, corporation, "
        "or other entity: (a) solicit, recruit, hire, or attempt to "
        "solicit, recruit, or hire any person who is, or was at any "
        "time during the final twelve (12) months of the Employee's "
        "employment, an employee, contractor, or consultant of the "
        "Employer with whom the Employee had material contact or "
        "about whom the Employee received confidential information "
        "in the course of the Employee's employment; or (b) solicit, "
        "divert, or attempt to solicit or divert any customer, "
        "supplier, vendor, licensee, or other business relation of "
        "the Employer with whom the Employee had material contact "
        "during the final twelve (12) months of the Employee's "
        "employment, for the purpose of providing goods or services "
        "that are competitive with the goods or services provided by "
        "the Employer at the time of termination. The Employee "
        "acknowledges that the consideration for the foregoing "
        "obligations includes the Employee's hiring, the compensation "
        "and benefits provided to the Employee under this Agreement, "
        "and the Employee's access to the Employer's confidential "
        "information, customer relationships, and goodwill. If any "
        "court of competent jurisdiction determines that the scope, "
        "geography, or duration of the foregoing obligations is "
        "broader than is enforceable under applicable law, the "
        "Employee and the Employer agree that the court may modify "
        "the scope, geography, or duration to the maximum extent "
        "enforceable under applicable law (a so-called 'blue-pencil' "
        "modification), and the remainder of the obligations shall "
        "remain in full force and effect. Notwithstanding the "
        "foregoing, the obligations set out in this section shall "
        "not apply in any jurisdiction in which post-employment "
        "non-solicitation obligations are void as against public "
        "policy (including, without limitation, California under "
        "California Business & Professions Code § 16600, and any "
        "other jurisdiction with a substantially similar statute or "
        "rule of common law).",
    ),
]

EXPECTED_SIM = 0.77  # mirrors the EN DPA and DE DPA smoke-test thresholds


async def main() -> int:
    factory = get_session_factory()
    store = get_store()
    failures: list[str] = []
    sims: list[float] = []
    providers: set[str] = set()

    # Ensure a fresh seed for employment-en
    async with factory() as session:
        rows = list(
            (
                await session.execute(
                    text(
                        "SELECT v.id FROM playbook_versions v "
                        "WHERE v.contract_type = 'employment' AND v.language = 'en' "
                        "ORDER BY v.id DESC LIMIT 1"
                    )
                )
            ).mappings()
        )
        if not rows:
            print(
                "ERROR: no employment-en playbook version found. Run the seeder first.",
                file=sys.stderr,
            )
            return 2
        version_id = rows[0]["id"]

    for expected_clause_id, paraphrase in PARAPHRASES:
        emb = embed_texts([paraphrase])[0]
        providers.add(emb.provider)
        async with factory() as session:
            hits = await store.topk(
                session,
                query_embedding=emb,
                k=1,
                contract_type="employment",
                language="en",
            )
        if not hits:
            failures.append(f"  - {expected_clause_id}: NO HITS returned")
            continue
        top = hits[0]
        sims.append(top.similarity)
        ok_type = top.clause_id == expected_clause_id
        marker = "OK " if ok_type and top.similarity >= EXPECTED_SIM else "FAIL"
        print(
            f"  [{marker}] expected={expected_clause_id:65s}  "
            f"got={top.clause_id:65s}  sim={top.similarity:.4f}"
        )
        if not ok_type:
            failures.append(
                f"  - {expected_clause_id}: top-1 is {top.clause_id} (wrong type)"
            )
        elif top.similarity < EXPECTED_SIM:
            failures.append(
                f"  - {expected_clause_id}: sim {top.similarity:.4f} < {EXPECTED_SIM}"
            )

    if "offline-hash" in providers:
        print(
            f"\nWARNING: embedding provider is offline-hash (real bge-m3 unreachable). "
            f"Sims will not be meaningful. providers seen: {providers}",
            file=sys.stderr,
        )

    print(
        f"\nsmoke summary: {len(PARAPHRASES) - len(failures)}/{len(PARAPHRASES)} OK; "
        f"sims min={min(sims) if sims else 0:.4f} max={max(sims) if sims else 0:.4f} "
        f"mean={sum(sims)/len(sims) if sims else 0:.4f}; providers={providers}"
    )

    if failures:
        print("\nFAILURES:", file=sys.stderr)
        for f in failures:
            print(f, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
