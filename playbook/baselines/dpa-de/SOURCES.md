# DE DPA Playbook Baselines — Quellen

Dieses Dokument dokumentiert die Provenienz für jede deutsch-
sprachige DPA-Baseline unter `playbook/baselines/dpa-de/`. Die
harte Regel der Karte, in Anlehnung an das EN-Set
(Karte t_45151f58) und das Phase-4-DE-NDA-Muster, lautet:
„Jede Baseline muss eine echte öffentliche Quelle haben. Keine
‚sieht plausibel aus'-Vorlagen von beliebigen Webseiten." Jede
Baseline hier lässt sich auf eine öffentliche Quelle
zurückführen, die unabhängig zitierbar und überprüfbar ist.
Abrufdatum für alle sechs ist der 2026-06-09; das
`retrieval_date`-Feld in jedem YAML spiegelt diesen Wert.

## Quellenübersicht

| Klausurtyp | Quelle | Quellenart | Warum eine öffentliche Quelle |
|---|---|---|---|
| `dpa_controller_processor_designation` | [Art. 28 DSGVO](https://eur-lex.europa.eu/legal-content/DE/TXT/HTML/?uri=CELEX:32016R0679#Art.28) (Abs. 1–3) | EU-Verordnung (EUR-Lex CELEX:32016R0679, deutsche Sonderausgabe) | Verordnungstext gemäß Art. 8(1) RBÜ gemeinfrei; EU-Open-Data-Politik (Beschluss 2011/833/EU) bekräftigt dies. Die deutsche Sonderausgabe (Amtsblatt L 119 vom 4.5.2016) ist die amtliche deutsche Fassung. Die Pflichtinhalts-Checkliste des Art. 28 Abs. 3 ist der *statutarische* Anker jeder deutschsprachigen AVV. |
| `dpa_subprocessor_consent` | [EDPB-Leitlinien 07/2020, v2.0 (DE)](https://www.edpb.europa.eu/system/files/2023-10/edpb_guidelines_202007_controllerprocessor_final_de.pdf) § 6 | EDPB-Leitlinien (PDF, 859 KB, deutsche Fassung) | Verabschiedet vom Europäischen Datenschutzausschuss (gemeinsames Gremium der nationalen Aufsichtsbehörden) am 7. Juli 2021; die maßgebliche nicht-verbindliche Auslegung des Mechanismus der allgemeinen schriftlichen Genehmigung gemäß Art. 28 Abs. 2 DSGVO. Die deutsche Fassung wird vom EDPB auf derselben Domain wie die englische Version gehostet. |
| `dpa_transfer_mechanism` | [EU SCCs 2021/914, Modul Zwei (DE)](https://eur-lex.europa.eu/legal-content/DE/TXT/HTML/?uri=CELEX:32021D0914) | Durchführungsbeschluss der Kommission (EUR-Lex CELEX:32021D0914, deutsche Fassung im Amtsblatt L 199 DE) | Die Standardvertragsklauseln nach Schrems II; seit 27. Dezember 2022 für neue Übermittlungen verpflichtend. Modul Zwei (Verantwortlicher an Auftragsverarbeiter) ist der einschlägige Übermittlungsmechanismus für jeden kommerziellen Drittland-Auftragsverarbeiter. Die deutsche Amtsblatt-Fassung ist die amtliche deutsche Übersetzung; die BAnz-AT-Veröffentlichung (Bundesanzeiger AT 07.06.2021) spiegelt die EUR-Lex-DE-Fassung. |
| `dpa_breach_notification` | [Art. 33 DSGVO](https://eur-lex.europa.eu/legal-content/DE/TXT/HTML/?uri=CELEX:32016R0679#Art.33) (Abs. 1–5) | EU-Verordnung (EUR-Lex CELEX:32016R0679, deutsche Sonderausgabe) | Die 72-Stunden-Frist des Verantwortlichen gegenüber der Aufsichtsbehörde ist die meistzitierte Einzeltatsache jeder AVV. Verordnungstext gemeinfrei; Baseline ergänzt das empfohlene 24-Stunden-Innenfenster Auftragsverarbeiter-an-Verantwortlicher gemäß EDPB-Leitlinien 9/2022 § 3.4. |
| `dpa_audit_rights` | [DSK-Kurzpapier Nr. 13](https://www.datenschutzkonferenz-online.de/media/kp/dsk_kpnr_13.pdf), S. 3–4 | DSK-Praktiker-Infopapier (PDF, 5 Seiten) | Gemeinsame Veröffentlichung der deutschen Bundes- und Landesdatenschutzbehörden; maßgebliche Auslegung des Art. 28 Abs. 3 lit. h DSGVO auf Praktiker-Ebene für den deutschsprachigen Markt. Frei zugängliches PDF, keine Registrierung. |
| `dpa_subprocessor_flowdown` | [§ 62 Abs. 4 BDSG 2018](https://www.gesetze-im-internet.de/bdsg_2018/__62.html) | Bundesdatenschutzgesetz, nationale Konkretisierung (gesetze-im-internet.de, BMJ/BfJ) | Die nationale Kodifikationsregel zur EU-Art. 28 Abs. 4 DSGVO-Pflicht, im deutschen Vertragsrecht unmittelbar anwendbar. Bundesgesetzestexte sind gemäß § 5 UrhG vom deutschen Urheberrecht ausgenommen; die Veröffentlichung auf gesetze-im-internet.de erfolgt ohne Nutzungsbeschränkung. Diese Baseline ergänzt die EN-Karte (t_45151f58), die das Einwilligungs-Tor im EN-Set abdeckt; im DE-Set deckt EDPB-DE das Tor und BDSG § 62 Abs. 4 die Weiterreichung ab. |

**Sechs Baselines, vier Quellenarten:** EU-Verordnung (mit
deutscher Sonderausgabe), EDPB-Leitlinien (deutsche Fassung),
Durchführungsbeschluss der Kommission (deutsche Amtsblatt-
Fassung), DSK-Praktiker-Infopapier, Bundesgesetzestext. Die
Quellenstreuung spiegelt das Phase-4-DE-NDA-Muster (5 Baselines,
5 unterschiedliche Quell-Hosts) und folgt der EN-Karte
(t_45151f58), die 2 GDPR-Artikel als Co-gehostet zulässt,
wenn sie unterschiedliche Inhalte abdecken (hier: Art. 28
und Art. 33 DSGVO auf derselben EUR-Lex-Seite, sowie Art. 28
DSGVO und die EU-SCCs auf der EUR-Lex-Domain).

## Warum diese Quellenstreuung die richtige für eine deutschsprachige DPA-Baseline ist

Die „echte öffentliche Quelle"-Regel der Karte wird hier
umgesetzt als: (a) der Quelleninhalt ist tatsächlich
öffentlich (keine Paywall, keine Registrierung, keine
Gebühr), (b) die Quelle hat anerkannte rechtliche Autorität
in der deutschsprachigen DPA-Praxis, und (c) kein einzelnes
Dokument deckt mehr als einen Klausurtyp ab. Die sechs
Quellen oben erfüllen alle drei Kriterien.

Die drei statutarischen Anker (Art. 28 DSGVO, Art. 33 DSGVO
und die EU SCCs 2021/914 in der deutschen Amtsblatt-Fassung)
sind die tragendsten — jede deutschsprachige AVV-Vorlage
(IAPP-Modellverträge, Big-4-Muster, SaaS-AGB) muss die
Pflichtinhalts-Checkliste des Art. 28 umsetzen, die
72-Stunden-Melderegel des Art. 33 beachten und seit Dezember
2022 die EU-SCCs für Drittlandübermittlungen einsetzen. Die
EDPB-Leitlinien 7/2020 füllen die Praktiker-Ebene für den
Einwilligungs-Mechanismus (allgemeine vs. spezifische
Genehmigung) aus, den der Verordnungstext offenlässt. Das
DSK-Kurzpapier Nr. 13 ist die deutsche DPO-Auslegung der
Audit-Rechte, die in kommerziellen Vorlagen am häufigsten mit
vager Sprache gestaltet werden — die DSK bietet die
sauberste öffentliche Artikulation der drei akzeptablen
Varianten (vor Ort, nur Zertifizierung, nur Auskunft). Das
BDSG 2018 § 62 Abs. 4 ist die nationale Konkretisierung der
Weiterreichungs-Pflicht an Unterauftragsverarbeiter, die
nicht-öffentliche Stellen unmittelbar bindet.

Eine private Kanzlei-AVV-Vorlage (z. B. die „Muster"-Seiten
auf einer Big-4-Website) wurde erwogen und aus zwei Gründen
verworfen: (1) Es handelt sich um Marketingmaterial einer
einzelnen Kanzlei und nicht um eine neutrale/aufsichts-
behördliche/statutarische Quelle, und (2) die Verwendung
derselben Vorlage für zwei Klausurtypen hätte die Quellen-
streuung auf vier unterschiedliche Quellen für sechs
Baselines kollabieren lassen, was die
„6 echte-öffentliche-Quelle"-Regel der Karte gerade
verhindern will.

## Was dieses Verzeichnis NICHT abdeckt (außerhalb des Kartenumfangs)

- Die verbleibenden 3 `dpa_*`-Klausurtypen aus der
  Phase-5-Taxonomie (`dpa_international_transfer`,
  `dpa_data_subject_rights`, `dpa_data_return_deletion`) —
  siehe `GAP.md` in diesem Verzeichnis für die Begründung
  und die Folgekarte.
- Die EN-Sprachäquivalente dieser sechs Baselines — das ist
  die Karte t_45151f58, bereits abgeschlossen.
- Die Counterparty-Matrix (4 Spalten × 9 dpa_*-Werte) —
  separate Karte (`t_counterparty_matrix`).
- Das Eval-Set (3 öffentliche + 2 synthetische DE-AVVs +
  Golden-YAMLs) — separate Karte.
- Der Matrix-bewusste Deviation-Spotter-Prompt — separate
  Karte.
- AVV-Verträge (`examples/contracts/public-dpa-de/`,
  `examples/contracts/synthetic-dpa-de/`) — separate Karte.

## Lizenzhinweis für nachgelagerte Konsumenten

Drei der sechs Quellen (Art. 28 DSGVO, Art. 33 DSGVO und die
EU SCCs 2021/914 in der deutschen Amtsblatt-Fassung) sind
EU-Rechtsakte im Gemeinwohl gemäß Art. 8(1) RBÜ und unter
der EU-Open-Data-Politik (Beschluss 2011/833/EU); frei
wiederverwendbar ohne Einschränkung außer Quellenangabe. Die
vierte (EDPB-Leitlinien 07/2020 in der deutschen Fassung)
ist eine EDPB-Veröffentlichung unter derselben Open-Access-
Politik, wiederverwendbar mit Quellenangabe „EDPB-Leitlinien
07/2020, v2.0 (2021-07-07), deutsche Fassung". Die fünfte
(DSK-Kurzpapier Nr. 13) ist ein gemeinsames
Bundes-Landes-DPO-Praktiker-Infopapier, das als frei
zugängliches PDF unter „Datenlizenz Deutschland —
Namensnennung — Version 2.0" auf der DSK-Website vertrieben
wird. Die sechste (BDSG 2018) ist ein Bundesgesetz, gemäß
§ 5 UrhG vom deutschen Urheberrecht ausgenommen.

Keine der Provenienz-URLs erfordert Registrierung, Zahlung
oder das Akzeptieren von Click-Through-Bedingungen. Das
Seed-Skript und die Seeder-Logs behandeln den Inhalt als
frei verwendbar für interne Baseline-Zwecke. Die
IAPP-Modellvertragsbibliothek, die frühere Fassung der EDPB-
Leitlinien 07/2020 (v1.0, 2020-09-02) und die SCC-Q&A der
Kommission wurden während der Erstellung als sekundäre
Querverweise erwogen, sind aber nicht die *primäre* Quelle
für irgendeine Baseline; ihre URLs sind im `notes`-Feld der
jeweiligen Baseline vermerkt, soweit der Querverweis
praktisch relevant ist.
