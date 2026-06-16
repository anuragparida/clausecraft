"""Smoke test for the DE DPA baselines (Phase 5 card t_70c2599d).

For each of the 6 DE DPA baselines, embed a paraphrased version of
the canonical clause, query the playbook store for the top-1 hit
filtered by ``contract_type=dpa, language=de``, and assert that:

  (a) the top-1 hit is the expected baseline (paraphrase → original
      retrieval), and
  (b) the cosine similarity is >= 0.77 (mirrors the EN card's
      smoke-test threshold from t_45151f58).

This is a manual smoke test (not part of the pytest suite) — it
needs the real bge-m3 provider reachable and a fresh seed. Run
from the repo root via:

  .venv-test/bin/python -m scripts.smoke_dpa_de  # noqa: E402

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
PARAPHRASES: list[tuple[str, str]] = [
    (
        "verantwortlicher-auftragsverarbeiter-zuordnung-art-28-3",
        # Paraphrase: shift from "Der Kunde" to "Der Auftraggeber" and
        # compress the "im Auftrag" / "auf Weisung" structure.
        "Der Auftraggeber ist im Sinne dieses Vertrags der "
        "Verantwortliche und der Dienstleister ist Auftragsverarbeiter "
        "personenbezogener Daten im Sinne der DSGVO. Der "
        "Auftragsverarbeiter darf personenbezogene Daten nur nach "
        "schriftlicher Weisung des Verantwortlichen verarbeiten, auch "
        "bei Übermittlungen in Drittländer, soweit nicht Unionsrecht "
        "oder nationales Recht ihn zur Verarbeitung verpflichtet. "
        "Eine Verarbeitung zu anderen Zwecken als den dokumentierten "
        "Weisungen ist unzulässig.",
    ),
    (
        "unterauftragsverarbeiter-vorherige-schriftliche-genehmigung-art-28-2",
        "Der Auftragsverarbeiter darf keinen Subunternehmer ohne "
        "vorherige ausdrückliche schriftliche Zustimmung des "
        "Verantwortlichen beauftragen. Bei allgemeiner Genehmigung "
        "ist der Verantwortliche über jeden Wechsel rechtzeitig zu "
        "informieren, damit er widersprechen kann. Wird ein "
        "Unterauftragsverarbeiter beauftragt, sind diesem dieselben "
        "Datenschutzpflichten vertraglich aufzuerlegen. Die "
        "Haftung des Haupt-Auftragsverarbeiters gegenüber dem "
        "Verantwortlichen bleibt unberührt.",
    ),
    (
        "unterauftragsverarbeiter-weiterreichungspflicht-bdsg-62-abs-4",
        "Beauftragt der Auftragsverarbeiter einen weiteren "
        "Auftragsverarbeiter, muss er diesem dieselben vertraglichen "
        "Pflichten auferlegen, die er gegenüber dem Verantwortlichen "
        "übernommen hat. Dies umfasst die weisungsgebundene "
        "Verarbeitung, Vertraulichkeit, Unterstützung bei "
        "Betroffenenrechten, Rückgabe oder Löschung der Daten nach "
        "Ende der Verarbeitung, Nachweispflichten, Ermöglichung von "
        "Überprüfungen sowie die Einhaltung der "
        "Sicherheitsmaßnahmen. Bei Pflichtverletzungen des "
        "Unterauftragsverarbeiters haftet der beauftragende "
        "Auftragsverarbeiter gegenüber dem Verantwortlichen.",
    ),
    (
        "sccs-modul-zwei-verantwortlicher-an-auftragsverarbeiter",
        "Die Parteien vereinbaren die Geltung der "
        "EU-Standardvertragsklauseln gemäß Durchführungsbeschluss "
        "(EU) 2021/914, Modul 2 (Übermittlung vom Verantwortlichen "
        "zum Auftragsverarbeiter). Die Standardvertragsklauseln "
        "gelten für Datenübermittlungen vom EWR-Verantwortlichen an "
        "den Auftragsverarbeiter in einem Drittland ohne "
        "Angemessenheitsbeschluss. Die Anhänge I bis III sind "
        "Anlage zum Vertrag. Bei Konflikten mit anderen "
        "Vertragsbestimmungen gehen die SCCs hinsichtlich der "
        "Drittlandübermittlung vor.",
    ),
    (
        "auftragsverarbeiter-an-verantwortlicher-meldung-datenschutzverletzung-72-stunden",
        "Eine Datenschutzverletzung ist dem Verantwortlichen "
        "unverzüglich, spätestens 24 Stunden nach Bekanntwerden, "
        "zu melden. Die Meldung muss die Art der Verletzung, "
        "betroffene Kategorien und Anzahl der Datensätze, "
        "wahrscheinliche Folgen sowie Gegenmaßnahmen beschreiben. "
        "Der Verantwortliche muss innerhalb von 72 Stunden die "
        "Aufsichtsbehörde informieren und gegebenenfalls "
        "betroffene Personen benachrichtigen. Eine Offenlegung "
        "gegenüber Dritten bedarf der schriftlichen Zustimmung "
        "des Verantwortlichen.",
    ),
    (
        "verantwortlicher-audit-rechte-art-28-3-h",
        "Der Auftragsverarbeiter hat dem Verantwortlichen alle "
        "Informationen zur Verfügung zu stellen, die zum Nachweis "
        "der Einhaltung der DSGVO-Pflichten erforderlich sind, und "
        "Audits einschließlich Vor-Ort-Inspektionen zu ermöglichen. "
        "Eine angemessene Vorlaufzeit (mindestens 30 Kalendertage) "
        "ist einzuhalten, außer bei konkreten Vorfällen. Die "
        "Prüfung umfasst Aufzeichnungen, Zertifizierungen (ISO "
        "27001, SOC 2) und Befragungen. Die Audit-Rechte gelten "
        "auch für die Unterauftragsverarbeiter des "
        "Auftragsverarbeiters.",
    ),
]

EXPECTED_SIM = 0.77  # mirrors the EN card's smoke-test threshold


async def main() -> int:
    factory = get_session_factory()
    store = get_store()
    failures: list[str] = []
    sims: list[float] = []
    providers: set[str] = set()

    # Ensure a fresh seed for dpa-de
    async with factory() as session:
        rows = list(
            (
                await session.execute(
                    text(
                        "SELECT v.id FROM playbook_versions v "
                        "WHERE v.contract_type = 'dpa' AND v.language = 'de' "
                        "ORDER BY v.id DESC LIMIT 1"
                    )
                )
            ).mappings()
        )
        if not rows:
            print("ERROR: no dpa-de playbook version found. Run the seeder first.", file=sys.stderr)
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
                contract_type="dpa",
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
