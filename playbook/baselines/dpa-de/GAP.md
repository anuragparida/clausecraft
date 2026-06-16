# DE DPA Playbook Baselines — Gap-Analyse

Dieses Dokument dokumentiert die drei `dpa_*`-Klausurtypen aus
der Phase-5-Taxonomie, die NICHT durch eine Baseline in
diesem Verzeichnis abgedeckt sind, die Begründung der Lücke
und die geplante Folgekarte.

## Die drei fehlenden Baselines

Die Phase-5-Klausurtaxonomie (`docs/15-clause-taxonomy-
phase5.md`) führt 9 `dpa_*`-Werte ein. Dieses Verzeichnis
liefert Baselines für 6 davon:

- `dpa_controller_processor_designation`
- `dpa_subprocessor_consent`
- `dpa_subprocessor_flowdown`
- `dpa_transfer_mechanism`
- `dpa_breach_notification`
- `dpa_audit_rights`

Die folgenden 3 sind **nicht** hier abgedeckt und benötigen
Folgearbeit:

| Klausurtyp | Warum nicht in diesem Verzeichnis | Wo es landen wird |
|---|---|---|
| `dpa_international_transfer` | Operative-Übermittlungs-Pflichtklausel. Die *Mechanismus*-Baseline oben (EU SCCs 2021/914 Modul Zwei) ist die Meta-Klausel; die *operative* Übermittlungspflicht ist der Hauptteil der SCCs-Klauseln 8.1–8.9 (für Drittlandübermittlungen). Der Hauptteil der SCCs ist als einzelne Baseline zu lang, um ein nützliches Deviation-Spotter-Ziel zu sein; der Spotter vergleicht aktuell gegen die SCCs-Modul-Zwei-Präambel, und der vollständige operative Hauptteil wird in der Matrix als eine einzige „Modul-Hauptteil"-Abweichung markiert. Eine separate Baseline dafür würde eine Zusammenfassung der Klauseln 8.1–8.9 erfordern, die zu viel strukturelle Details verliert. | Entweder Erweiterung der bestehenden `dpa_transfer_mechanism`-Baseline um eine operative-Hauptteil-Zusammenfassung als zweiten `clauses:`-Eintrag, oder Beibehaltung als „durch die Mechanismus-Baseline abgedeckt"-Residuum — siehe Entscheidungs-Log unten. |
| `dpa_data_subject_rights` | Recht auf Auskunft / Recht auf Löschung / Widerspruchs-Mechanismus. Die Klausel ist strukturell einfach (der Auftragsverarbeiter muss den Verantwortlichen bei der Beantwortung von Betroffenenrechts-Anfragen unterstützen, mit einer typischen SLA von „unverzüglich, in jedem Fall innerhalb von 30 Tagen"), aber die öffentlichen Quellen sind verstreut: Art. 12–22 DSGVO + Art. 28 Abs. 3 lit. e DSGVO + EDPB-Leitlinien zum Recht auf Löschung (5/2019) + EDPB-Leitlinien zur Einwilligung (05/2020). Die Kombination von vier Quellen in einer Baseline ist machbar, aber eine einzige Quellen-Zitat-Kombination wäre sauberer. | Folgekarte `t_dpa_data_subject_rights_baseline` (vorgeschlagen), soll im dpa-de-Verzeichnis landen, damit beide Sprachen gemeinsam ausgeliefert werden. |
| `dpa_data_return_deletion` | Beendigungs- Rückgabe-oder-Löschungs-Mechanismus. Art. 28 Abs. 3 lit. g DSGVO ist der statutarische Anker; die Praktiker-Ebenen-Varianten (nur löschen, nur zurückgeben, zurückgeben-dann-löschen mit Zertifizierung, zurückgeben nach Wahl des Verantwortlichen) sind gut dokumentiert in den EDPB-Leitlinien 07/2020 und im DSK-Kurzpapier. Dasselbe Problem wie `dpa_data_subject_rights` — mehrere Quellen, würde von einem Ein-Quellen-Design profitieren. | Dieselbe Folgekarte wie `dpa_data_subject_rights` (vorgeschlagen: `t_dpa_post_engagement_baselines`). |

## Entscheidungs-Log

Die „6 Baselines oder 3 + GAP.md"-Hedge im Karteibody
existiert, weil öffentlich-quellliche DE-AVVs seltener sind
als NDA-Vorlagen. Nach der Recherche am 2026-06-09 war die
tatsächliche Knappheit *nicht* ein Mangel an öffentlichen
Quellen, sondern ein Mangel an *sauberer Einzelquelle-pro-
Klausel*-öffentlichen Autoritäten. Art. 28 und Art. 33 DSGVO
+ EU SCCs 2021/914 (DE) + EDPB-Leitlinien 7/2020 (DE) + DSK-
Kurzpapier Nr. 13 + BDSG 2018 § 62 sind sechs unterschiedliche,
aufsichtsbehördlich-gradige öffentliche Quellen, die sich
sauber sechs Baselines zuordnen lassen. Die drei verbleibenden
`dpa_*`-Werte berühren jeweils mehr als eine Quelle, und eine
Zwangszuordnung zu einer einzelnen Quelle hätte die
Quellenstreuung auf 4 Quellen für 9 Klausurtypen kollabieren
lassen — was die per-Baseline-Provenienz geschwächt, nicht
gestärkt hätte.

Die Entscheidung ist daher: 6 Baselines jetzt ausliefern
(die „6 echte-öffentliche-Quelle"-Branch der Karten-Hedge),
und die verbleibenden 3 in einer einzelnen Folgekarte
anlegen, die ein 2-Klauseln-Paar (`dpa_data_subject_rights` +
`dpa_data_return_deletion`) unter einer kombinierten Quelle
(Art. 28 DSGVO + EDPB-Leitlinien 7/2020 + 5/2019) sowie eine
„durch-Mechanismus-abgedeckt"-Notiz für den SCCs-operativen-
Hauptteil (`dpa_international_transfer`) liefern wird. Das
EN-Baseline-Verzeichnis enthält seinerseits 5 Baselines; das
DE-Verzeichnis enthält 6 Baselines (einschließlich
`dpa_subprocessor_flowdown`, das im EN-Verzeichnis
ausgespart ist, um Duplikation zu vermeiden — siehe
`t_45151f58/GAP.md`).

## Was Helenas Review-Karte erwarten sollte

- 6 Baselines in diesem Verzeichnis parsen sauber und lösen
  auf Phase-5-`dpa_*`-Enum-Werte auf.
- Die SOURCES.md liefert 6 unterschiedliche, zitierbare
  öffentliche Quellen über 4 unterschiedliche Hosts.
- Die 3 fehlenden `dpa_*`-Werte sind in dieser Datei mit
  einer geplanten Folgekarte dokumentiert.
- Der Spotter kann, wenn er auf eine reale AVV gerichtet
  wird, mindestens eine dieser 6 Baselines abrufen und
  zitieren (Smoke-Test folgt, sobald die Eval-Set-Karte
  ausgeliefert wird).

## Was NICHT als „Lücke" zählt, die es wert ist, gemeldet zu werden

- Eine *strengere* Gestaltungswahl in einer Vertragsklausel
  (z. B. eine kürzere Auftragsverarbeiter-an-Verantwortlicher-
  Meldungsfrist als 24 Stunden) ist keine Lücke; sie ist eine
  strenger-als-Baseline-Position und die Matrix soll sie
  akzeptieren.
- Eine *losere* Gestaltungswahl in einer Vertragsklausel (z. B.
  „unverzüglich" statt einer 24-Stunden-Frist) ist eine
  Abweichung, die in der Matrix zu markieren ist, nicht eine
  Lücke im Baseline-Set.
- Eine vertragspartnerspezifische Carve-Out (z. B.
  gesundheitswesenspezifische Datenlokalisierungs-Anforderungen)
  wird durch die Counterparty-Matrix behandelt, nicht durch
  Hinzufügen weiterer Baselines.
