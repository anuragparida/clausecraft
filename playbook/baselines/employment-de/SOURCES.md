# DE Employment Playbook Baselines — Quellen

Dieses Dokument dokumentiert die Provenienz für jede deutsch-
sprachige Employment-Baseline unter
`playbook/baselines/employment-de/`. Die harte Regel der Karte,
in Anlehnung an das EN-Set (Karte t_d23d222d), das DE-DPA-Set
(Karte t_70c2599d) und das Phase-4-DE-NDA-Muster, lautet:
„Jede Baseline muss eine echte öffentliche Quelle haben. Keine
‚sieht plausibel aus'-Vorlagen von beliebigen Webseiten." Jede
Baseline hier lässt sich auf eine öffentliche Quelle
zurückführen, die unabhängig zitierbar und überprüfbar ist.
Abrufdatum für alle fünf ist der 2026-06-10; das
`retrieval_date`-Feld in jedem YAML spiegelt diesen Wert.

## Quellenübersicht

| Klausurtyp | Quelle | Quellenart | Warum eine öffentliche Quelle |
|---|---|---|---|
| `employment_notice_period` | [§ 622 BGB — Kündigungsfristen bei Arbeitsverhältnissen](https://www.gesetze-im-internet.de/bgb/__622.html) (Abs. 1–6) | Bundesgesetz (gesetze-im-internet.de, BMJ/BfJ) | Die zentrale Norm für gesetzliche Mindestkündigungsfristen im deutschen Arbeitsrecht: Grundfrist 4 Wochen zum Fünfzehnten/Ende des Kalendermonats (Abs. 1), gestaffelte Verlängerung für arbeitgeberseitige Kündigungen nach Betriebszugehörigkeit (Abs. 2), verkürzte Probezeit-Frist 2 Wochen bei max. 6 Monaten (Abs. 3), und einzelvertragliches Unterschreitungsverbot für Kleinbetriebe und Aushilfen (Abs. 5). Bundesgesetzestext, gemäß § 5 Abs. 1 UrhG vom deutschen Urheberrecht ausgenommen. |
| `employment_remuneration` | [§ 611a Abs. 2 BGB — Vergütungspflicht](https://www.gesetze-im-internet.de/bgb/__611a.html) | Bundesgesetz (gesetze-im-internet.de, BMJ/BfJ) | Die statutarische Verankerung der Vergütungspflicht des Arbeitgebers: "Der Arbeitgeber ist zur Zahlung der vereinbarten Vergütung verpflichtet." Eingeführt durch das Arbeitsrechtsmodernisierungsgesetz 2017, in Kraft seit 1. Januar 2018. Bundesgesetzestext, gemäß § 5 Abs. 1 UrhG vom deutschen Urheberrecht ausgenommen. |
| `employment_leave_entitlements` | [§ 3 BUrlG — Dauer des Urlaubs](https://www.gesetze-im-internet.de/burlg/__3.html) (Abs. 1–2) | Bundesgesetz (gesetze-im-internet.de, BMJ/BfJ) | Der gesetzliche Mindesturlaub von 24 Werktagen pro Kalenderjahr (Bemessungsgrundlage Sechs-Tage-Woche) ist die zentrale deutsche Urlaubsstatutarik. Die Umrechnung auf die heute übliche Fünf-Tage-Woche ergibt 20 Arbeitstage Mindesturlaub (BAG, ständige Rechtsprechung). Bundesgesetzestext, gemäß § 5 Abs. 1 UrhG vom deutschen Urheberrecht ausgenommen. |
| `employment_termination_for_cause` | [§ 626 BGB — Fristlose Kündigung aus wichtigem Grund](https://www.gesetze-im-internet.de/bgb/__626.html) (Abs. 1–2) | Bundesgesetz (gesetze-im-internet.de, BMJ/BfJ) | Die statutarische Definition des wichtigen Grundes für eine außerordentliche Kündigung (Abs. 1: "Tatsachen, auf Grund derer dem Kündigenden ... die Fortsetzung des Dienstverhältnisses ... nicht zugemutet werden kann") und die Zwei-Wochen-Ausschlussfrist ab Kenntnisnahme (Abs. 2). Bundesgesetzestext, gemäß § 5 Abs. 1 UrhG vom deutschen Urheberrecht ausgenommen. |
| `employment_non_solicitation` | [IHK Muster eines Arbeitsvertrages](https://www.ihk.de/blueprint/servlet/resource/blob/764306/02ef8855772d2df8a4c743b497776f4d/arbeitsvertrag-muster--data.pdf) (Stand: Januar 2025), § 12 (Verschwiegenheitspflicht mit Vertragsstrafe) und § 13 (Nebentätigkeit) | IHK-Modellvertrag (deutsche Industrie- und Handelskammern, offizielles Musterdokument für Mitgliedsunternehmen) | Das einzige frei zugängliche deutsche Muster für eine nachvertragliche Verschwiegenheits- und Wettbewerbsbeschränkungs-Klausel in einer integrierten Vertragsform. § 12 deckt die post-vertragliche Verschwiegenheit inkl. Vertragsstrafen-Mechanismus ab; § 13 die Anzeige- und Zustimmungspflicht für Nebentätigkeiten. Die statutarische Berücksichtigungsschranke (§ 138 BGB AGB-Kontrolle für einseitige Kontaktaufnahme-Beschränkungen ohne Kompensation) ist in der Baseline-Anker-Logik integriert. |

**Fünf Baselines, zwei Quellenarten:** Vier
Bundesgesetzestexte auf gesetze-im-internet.de (BMJ/BfJ — das
amtliche deutsche Bundesjustizportal) und ein IHK-Modellvertrag
auf ihk.de (das offizielle Musterdokument der deutschen
Industrie- und Handelskammern). Die Quellenstreuung spiegelt
das EN-Set (Karte t_d23d222d: 4 × GOV.UK + 1 × ABA-Modell) und
das DE-DPA-Set (Karte t_70c2599d: 4 Quellenarten über 4 Hosts).
Die vier gesetze-im-internet.de-Treffer sind vier
*unterschiedliche Paragraphen unterschiedlicher Bundesgesetze*
(§ 622 BGB, § 611a BGB, § 3 BUrlG, § 626 BGB) auf derselben
amtlichen Domain — die Karte folgt der DE-DPA-Karten-Logik, die
mehrere unterschiedliche Dokumente auf derselben Domain
zulässt, wenn sie unterschiedliche Inhalte abdecken (vgl.
EUR-Lex mit Art. 28 DSGVO + Art. 33 DSGVO + EU SCCs).

## Warum diese Quellenstreuung die richtige für eine deutschsprachige Employment-Baseline ist

Die „echte öffentliche Quelle"-Regel der Karte wird hier
umgesetzt als: (a) der Quelleninhalt ist tatsächlich
öffentlich (keine Paywall, keine Registrierung, keine Gebühr),
(b) die Quelle hat anerkannte rechtliche Autorität in der
deutschsprachigen Arbeitsrechts-Praxis, und (c) kein einzelnes
Dokument deckt mehr als einen Klausurtyp ab. Die fünf Quellen
oben erfüllen alle drei Kriterien.

Die vier gesetze-im-internet.de-Anker (BGB § 622 für
Kündigungsfristen, BGB § 611a Abs. 2 für Vergütungspflicht,
BUrlG § 3 für Mindesturlaub, BGB § 626 für fristlose Kündigung)
sind die tragendsten — jeder deutschsprachige Arbeitsvertrag
muss die Mindestkündigungsfristen des § 622 BGB, die
Vergütungspflicht des § 611a BGB, den Mindesturlaub des § 3
BUrlG und das Verfahren der fristlosen Kündigung nach § 626
BGB einhalten. gesetze-im-internet.de ist das amtliche Portal
des Bundesministeriums der Justiz (BMJ) und des Bundesamts für
Justiz (BfJ) für die konsolidierte Fassung der deutschen
Bundesgesetze; die Veröffentlichung erfolgt gemäß § 5 Abs. 1
UrhG ohne Nutzungsbeschränkung.

Der IHK Musterarbeitsvertrag (Januar 2025) ist der deutsche
Modellvertrags-Anker, der dem ABA Model Employment Agreement
(US-Komparator im EN-Set) entspricht. Die deutschen IHKs sind
die gesetzlichen Selbstverwaltungskörperschaften der gewerblichen
Wirtschaft; ihre Musterverträge sind die praxisnahen Standard-
Referenzen für die deutsche KMU-Vertragsgestaltung. § 12
(Verschwiegenheitspflicht mit Vertragsstrafe) und § 13
(Nebentätigkeit) des IHK-Mustervertrags sind die einzige
öffentlich zugängliche, kostenlose und rechtlich eingeführte
deutsche Modellklausel-Struktur für die
Kontaktaufnahme-Beschränkung im nachvertraglichen Bereich; die
statutarischen Schranken (§ 138 BGB AGB-Kontrolle und § 74 HGB
Karenzentschädigung) sind in der Baseline als Plausibilitätsanker
integriert.

Eine private Kanzlei-Mustervertrags-Vorlage (z. B. die
„Arbeitsvertrag-Muster"-Seiten auf einer Big-4-Website oder
einer Online-Rechtsbibliothek) wurde erwogen und aus drei
Gründen verworfen: (1) Es handelt sich um Marketingmaterial
einer einzelnen Kanzlei und nicht um eine
neutrale/aufsichtsbehördliche/statutarische Quelle, (2) die
Kombination aus vier gesetzlichen Ankern und einem
Modellvertrags-Anker deckt die fünf Baselines
lückenlos ab, und (3) die Verwendung derselben Vorlage für
zwei Klausurtypen hätte die Quellenstreuung auf vier
unterschiedliche Quellen für fünf Baselines kollabieren
lassen, was die „5 echte-öffentliche-Quelle"-Regel der Karte
gerade verhindern will.

## Was dieses Verzeichnis NICHT abdeckt (außerhalb des Kartenumfangs)

- Die verbleibenden 6 `employment_*`-Klausurtypen aus der
  Phase-5-Taxonomie (`employment_probation`,
  `employment_garden_leave`, `employment_non_compete`,
  `employment_ip_assignment`,
  `employment_confidentiality_survival`,
  `employment_working_hours`) — siehe `GAP.md` in diesem
  Verzeichnis für die Begründung und die Folgekarten.
- Die EN-Sprachäquivalente dieser fünf Baselines — das ist
  die Karte t_d23d222d, bereits abgeschlossen.
- Die Counterparty-Matrix (4 Spalten × 11 employment_*-Werte) —
  separate Karte (`t_33ecfb34`, abgeschlossen).
- Das Eval-Set (3 öffentliche + 2 synthetische DE-Arbeitsverträge
  + Golden-YAMLs) — separate Karte (`t_dpa_eval_set` ist
  benachbart, aber DE-Employment-Eval ist noch nicht auf der
  Karteikarte).
- Der Matrix-bewusste Deviation-Spotter-Prompt — separate Karte.
- DE-Arbeitsverträge (`examples/contracts/public-employment-de/`,
  `examples/contracts/synthetic-employment-de/`) — separate
  Karte.

## Lizenzhinweis für nachgelagerte Konsumenten

Vier der fünf Quellen (die vier gesetze-im-internet.de-Treffer)
sind deutsche Bundesgesetzestexte, gemäß § 5 Abs. 1 UrhG vom
deutschen Urheberrecht ausgenommen; die Veröffentlichung
erfolgt durch das Bundesministerium der Justiz ohne
Nutzungsbeschränkung. Die fünfte (IHK Muster eines
Arbeitsvertrages) ist ein offizielles Musterdokument der
deutschen Industrie- und Handelskammern, frei zugänglich auf
ihk.de ohne Registrierung; die Verwendung erfolgt im Rahmen
der karte-eigenen Vorwort-Hinweise zur Eigenprüfung. Die
Baseline-Sprache in allen fünf YAMLs ist eine paraphrasierte
Verdichtung des Quellentextes, keine wortgetreue Übernahme.
Die seeder-Logik behandelt alle fünf Quellen als frei
wiederverwendbar für interne Baseline-Zwecke.

Das seeder-spezifische `license`-Feld pro Baseline spiegelt
die obige Aufteilung (vier Bundesgesetzestexte, ein
IHK-Modellvertrag).
