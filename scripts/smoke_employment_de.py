"""Smoke test for the DE Employment baselines (Phase 5 card t_84896561).

For each of the 5 DE Employment baselines, embed a paraphrased
version of the canonical clause, query the playbook store for
the top-1 hit filtered by ``contract_type=employment, language=de``,
and assert that:

  (a) the top-1 hit is the expected baseline (paraphrase → original
      retrieval), and
  (b) the cosine similarity is >= 0.77 (mirrors the EN Employment
      and DE DPA smoke-test thresholds from t_d23d222d and
      t_70c2599d).

This is a manual smoke test (not part of the pytest suite) — it
needs the real bge-m3 provider reachable and a fresh seed. Run
from the repo root via:

  .venv-test/bin/python -m scripts.smoke_employment_de  # noqa: E402

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
        "de-kuendigungsfrist-bgb-622",
        # Paraphrase: shift from "vier Wochen zum Fünfzehnten oder zum
        # Ende eines Kalendermonats" to "monatliche Kündigungsfrist von
        # vier Wochen" and reorder the tenure-staffel to start with the
        # 5-year bracket. Keep the § 622 BGB reference and the
        # Probezeit-2-Wochen carve-out.
        "Das Arbeitsverhältnis kann beiderseitig mit einer Frist von "
        "vier Wochen zu jedem Monatsende gekündigt werden. Im Falle "
        "einer Kündigung durch den Arbeitgeber verlängert sich diese "
        "Frist abhängig von der Dauer der Betriebszugehörigkeit: "
        "nach fünf Jahren Betriebszugehörigkeit auf zwei Monate zum "
        "Ende eines Kalendermonats, nach acht Jahren auf drei Monate, "
        "nach zehn Jahren auf vier Monate, nach zwölf Jahren auf fünf "
        "Monate, nach fünfzehn Jahren auf sechs Monate und nach "
        "zwanzig Jahren auf sieben Monate zum Monatsende. Während "
        "einer vereinbarten Probezeit, die höchstens sechs Monate "
        "betragen darf, gilt eine verkürzte Kündigungsfrist von "
        "zwei Wochen. Diese Fristen entsprechen den gesetzlichen "
        "Mindestkündigungsfristen gemäß § 622 BGB; eine kürzere "
        "Frist ist nur unter den engen Ausnahmen des § 622 Abs. 5 "
        "BGB (Aushilfe, Kleinbetrieb) zulässig. Eine längere "
        "Kündigungsfrist für den Arbeitnehmer als für den "
        "Arbeitgeber ist nach § 622 Abs. 6 BGB unwirksam.",
    ),
    (
        "de-verguetungspflicht-bgb-611a-abs-2",
        # Paraphrase: shift from "Bruttomonatsvergütung" to
        # "Bruttogehalt" and reorder the Fälligkeit-on-Monatsende
        # statement to before the bargeldlos clause. Keep the
        # § 611a Abs. 2 BGB anchor and the Mindestlohn reference.
        "Der Arbeitgeber hat dem Arbeitnehmer die im Arbeitsvertrag "
        "vereinbarte Vergütung für die erbrachte Arbeitsleistung zu "
        "zahlen. Die geschuldete Vergütung umfasst das vereinbarte "
        "Bruttogehalt sowie sämtliche im Arbeitsvertrag ausdrücklich "
        "geregelten weiteren Vergütungsbestandteile wie Zuschläge, "
        "Zulagen, Prämien, Urlaubs- und Weihnachtsgeld sowie "
        "vermögenswirksame Leistungen. Die Vergütung wird am Ende "
        "des jeweiligen Kalendermonats fällig und bargeldlos auf das "
        "vom Arbeitnehmer benannte Gehaltskonto überwiesen. Diese "
        "Vergütungspflicht des Arbeitgebers ergibt sich unmittelbar "
        "aus § 611a Abs. 2 BGB und ist nicht abdingbar. Eine "
        "einseitige Herabsetzung der vereinbarten Vergütung ist "
        "nur durch Änderungskündigung oder einvernehmliche "
        "Vertragsänderung möglich; eine Reduktion unter den "
        "gesetzlichen Mindestlohn nach dem Mindestlohngesetz ist "
        "stets unzulässig. Der Vergütungsanspruch wird durch "
        "Entgeltfortzahlung im Krankheitsfall und durch bezahlte "
        "Freistellungsansprüche nicht berührt.",
    ),
    (
        "de-mindesturlaub-burlg-3",
        # Paraphrase: shift from "24 Werktage" to "24 Werktage im
        # Kalenderjahr" and reorder the Fünf-Tage-Woche-Umrechnung
        # to after the Mindesturlaub statement. Keep the
        # 15-Monats-Verfallsregel for AU and the § 7 Abs. 4
        # BUrlG-Abgeltung.
        "Der Arbeitnehmer hat in jedem Kalenderjahr Anspruch auf "
        "einen gesetzlichen Mindesturlaub von mindestens 24 "
        "Werktagen, wobei Werktage im Sinne des § 3 Abs. 2 BUrlG "
        "alle Kalendertage sind, die nicht Sonn- oder gesetzliche "
        "Feiertage sind. Bei der heute üblichen Fünf-Tage-Woche "
        "entspricht dies 20 Arbeitstagen Mindesturlaub pro Jahr. "
        "Dieser gesetzliche Mindesturlaub dient der Erholung des "
        "Arbeitnehmers und kann nach der Rechtsprechung des "
        "Bundesarbeitsgerichts nur dann in das folgende Kalenderjahr "
        "übertragen werden, wenn der Arbeitnehmer den Urlaub aus "
        "betrieblichen Gründen oder wegen Arbeitsunfähigkeit nicht "
        "im laufenden Jahr nehmen konnte; in diesem Fall ist der "
        "Urlaub innerhalb der ersten drei Monate des Folgejahres "
        "nachzuholen. Der gesetzliche Mindesturlaub verfällt bei "
        "Arbeitsunfähigkeit erst 15 Monate nach Ende des "
        "Urlaubsjahres. Bei Beendigung des Arbeitsverhältnisses "
        "sind verbleibende gesetzliche Urlaubsansprüche nach § 7 "
        "Abs. 4 BUrlG abzugelten. Ein vertraglicher Zusatzurlaub "
        "über den gesetzlichen Mindesturlaub hinaus ist frei "
        "vereinbar.",
    ),
    (
        "de-fristlose-kuendigung-bgb-626",
        # Paraphrase: shift from "wichtiger Grund" to "wichtigen
        # Grundes" and reorder the Beispielliste to put
        # "Tätlichkeiten" first. Keep the Zwei-Wochen-Frist
        # and the § 626 BGB reference.
        "Das Arbeitsverhältnis kann von jeder Vertragspartei "
        "fristlos aus wichtigem Grund gemäß § 626 BGB gekündigt "
        "werden, wenn Tatsachen vorliegen, aufgrund derer der "
        "kündigenden Seite unter Berücksichtigung aller Umstände "
        "des Einzelfalls und unter Abwägung der beiderseitigen "
        "Interessen die Fortsetzung des Arbeitsverhältnisses bis "
        "zum Ablauf der ordentlichen Kündigungsfrist nicht "
        "zugemutet werden kann. Ein wichtiger Grund liegt nach der "
        "Rechtsprechung des Bundesarbeitsgerichts insbesondere vor "
        "bei Tätlichkeiten oder Beleidigungen gegenüber "
        "Vorgesetzten, Kollegen oder Kunden, Diebstahl, "
        "Unterschlagung oder Betrug zum Nachteil des Arbeitgebers, "
        "erheblicher Arbeitsverweigerung, vorsätzlichem oder grob "
        "fahrlässigem Verstoß gegen die arbeitsvertragliche "
        "Verschwiegenheitspflicht, Annahme von Schmiergeldern, "
        "beharrlicher Verletzung der Arbeitspflicht trotz "
        "Abmahnung sowie beharrlicher Unpünktlichkeit. Die "
        "außerordentliche Kündigung kann nur innerhalb einer "
        "Ausschlussfrist von zwei Wochen ab Kenntnis der "
        "maßgeblichen Tatsachen erfolgen; die Kündigung bedarf "
        "der Schriftform nach § 623 BGB.",
    ),
    (
        "de-nachvertragliche-verschwiegenheit-und-nebentaetigkeit-ihk-muster",
        # Paraphrase: shift from "Geschäftsgeheimnisse" to
        # "Betriebsgeheimnisse" and reorder the Vertragsstrafe
        # statement to after the Geheimhaltungspflicht statement.
        # Keep the § 138 BGB and § 74 HGB references and the
        # Karenzentschädigung mention.
        "Der Arbeitnehmer ist verpflichtet, sowohl während des "
        "bestehenden Arbeitsverhältnisses als auch nach dessen "
        "Beendigung über alle Betriebsgeheimnisse und vertraulichen "
        "Geschäftsangelegenheiten des Arbeitgebers Stillschweigen "
        "zu bewahren und diese Dritten nicht zugänglich zu machen, "
        "sofern er nicht ausdrücklich von der Geschäftsleitung "
        "dazu ermächtigt wird. Diese Geheimhaltungspflicht umfasst "
        "insbesondere technische und kaufmännische Informationen, "
        "Kunden- und Lieferantenbeziehungen, Preisgestaltungen, "
        "Verfahrens- und Produktentwicklungen sowie interne "
        "Geschäftsberichte. Für jeden schuldhaften Verstoß gegen "
        "die Verschwiegenheitspflicht hat der Arbeitnehmer eine "
        "Vertragsstrafe in angemessener Höhe, in der Regel eine "
        "Bruttomonatsvergütung, zu zahlen; die Geltendmachung "
        "weitergehenden Schadens bleibt vorbehalten. Die "
        "Verschwiegenheitspflicht besteht nach Beendigung des "
        "Arbeitsverhältnisses gemäß § 622 Abs. 6 BGB fort. "
        "Jede entgeltliche Nebentätigkeit ist dem Arbeitgeber "
        "vor ihrer Aufnahme unverzüglich in Textform anzuzeigen; "
        "nachvertragliche Kontaktaufnahmebeschränkungen "
        "(Kunden-, Lieferanten- oder Mitarbeiteransprache) "
        "bedürfen zu ihrer Wirksamkeit einer vertraglichen "
        "Kompensation und unterliegen der AGB-Kontrolle nach "
        "§ 138 BGB.",
    ),
]

EXPECTED_SIM = 0.77  # mirrors the EN Employment and DE DPA smoke-test thresholds


async def main() -> int:
    factory = get_session_factory()
    store = get_store()
    failures: list[str] = []
    sims: list[float] = []
    providers: set[str] = set()

    # Ensure a fresh seed for employment-de
    async with factory() as session:
        rows = list(
            (
                await session.execute(
                    text(
                        "SELECT v.id FROM playbook_versions v "
                        "WHERE v.contract_type = 'employment' AND v.language = 'de' "
                        "ORDER BY v.id DESC LIMIT 1"
                    )
                )
            ).mappings()
        )
        if not rows:
            print(
                "ERROR: no employment-de playbook version found. Run the seeder first.",
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
                language="de",
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
