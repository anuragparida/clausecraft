# DE Employment Playbook Baselines — Gap-Analyse

Dieses Dokument dokumentiert die sechs `employment_*`-Klausurtypen
aus der Phase-5-Taxonomie, die NICHT durch eine Baseline in
diesem Verzeichnis abgedeckt sind, die Begründung der Lücke
und die geplanten Folgekarten.

## Die sechs fehlenden Baselines

Die Phase-5-Klausurtaxonomie (`docs/15-clause-taxonomy-phase5.md`)
führt 11 `employment_*`-Werte ein. Dieses Verzeichnis liefert
Baselines für 5 davon:

- `employment_notice_period`
- `employment_remuneration`
- `employment_leave_entitlements`
- `employment_termination_for_cause`
- `employment_non_solicitation`

Die folgenden 6 sind **nicht** hier abgedeckt und benötigen
Folgearbeit:

| Klausurtyp | Warum nicht in diesem Verzeichnis | Wo es landen wird |
|---|---|---|
| `employment_probation` | Die Probezeit ist im DE-Set durch § 622 Abs. 3 BGB (Kündigungsfrist während vereinbarter Probezeit, max. 6 Monate) innerhalb der `employment_notice_period`-Baseline abgedeckt. Eine separate `employment_probation`-Baseline würde nur die Dauer- und Vertragsgestaltungs-Frage isolieren, nicht die statutarische Anker-Frage. Die EN-Karte hat `employment_probation` ausgespart, weil das UK-Äquivalent (ERA 1996 s.1(3)(d) Probezeitangabe in der schriftlichen Erklärung) ebenfalls in `employment_notice_period` und `employment_remuneration` mitverhandelt wird. | Folgekarte `t_employment_probation_baseline` (vorgeschlagen), die *sowohl* die DE- (BGB § 622 Abs. 3) als auch die UK-Seite (ERA 1996 s.1(3)(d)) zusammenführt. |
| `employment_garden_leave` | UK-spezifisches Konzept (ERA 1996 s.20(8)). Kein BGB-Äquivalent; die deutsche "Freistellung" ist verwandt, aber rechtlich eigenständig (vgl. IHK Mustervertrag § 14 Abs. 5, das die Freistellung unter Anrechnung von Urlaubsansprüchen und Arbeitszeitkonto-Guthaben regelt). Eine einzelne DE-Source kann den UK-Begriff nicht sauber abdecken; der UK-Anker gehört in eine UK+DE-Paar-Karte. | Folgekarte `t_employment_garden_leave_baseline` (vorgeschlagen), die *sowohl* die UK- (ERA 1996 s.20(8)) als auch die DE-Seite (IHK-Muster § 14 Abs. 5) zusammenführt. |
| `employment_non_compete` | DE-verankert durch BGB §§ 74 ff. HGB (Karenzentschädigung 50 %, Schriftform, max. 2 Jahre, klarer räumlicher Geltungsbereich). Der UK/US-Komparator (Restatement (Second) Contracts § 188 / UK common-law reasonableness) wäre eine schwächere Sekundärquelle, die die Quellenstreuung nicht stärkt. Eine einzelne Source pro Sprache reicht aus, aber die DE-Source ist die *load-bearing* — sie sollte mit der vollen Aufmerksamkeit behandelt werden, die das HGB-Verbot ohne Karenzentschädigung verdient. | `playbook/baselines/employment-de/` in einer Folgekarte `t_employment_non_compete_baseline`, die eine einzelne Baseline auf Basis BGB §§ 74 ff. HGB + BAG-Rechtsprechung zur Karenzentschädigung liefert. |
| `employment_ip_assignment` | DE-verankert durch das Arbeitnehmererfindungsgesetz (ArbNErfG), insbesondere § 29 ArbNErfG (Inanspruchnahme und separate Vergütungsberechnung). UK-Komparator: UK Patents Act 1977 s.39 + common-law assignment. Die DE-Quelle (ArbNErfG) ist die *load-bearing*; der UK-Komparator ist eine sinnvolle Sekundärquelle, die in einer UK+DE-Paar-Karte behandelt werden kann. | `playbook/baselines/employment-de/` in einer Folgekarte `t_employment_ip_assignment_baseline`, die *sowohl* die DE- (ArbNErfG) als auch die UK-Seite (Patents Act 1977) zusammenführt. |
| `employment_confidentiality_survival` | BGB § 622 Abs. 6 (Betriebsgeheimnisse nachvertraglich implied) + der IHK Mustervertrag § 12 (Verschwiegenheitspflicht mit Vertragsstrafe). Eine einzelne Source kann entweder die statutarische Mindestregel (BGB) ODER die vertragliche Erweiterung (IHK) abdecken, nicht beide. Die `employment_non_solicitation`-Baseline oben nutzt bereits § 12 IHK + § 622 Abs. 6 BGB für die *post-vertragliche Verschwiegenheit*; eine separate `employment_confidentiality_survival`-Baseline würde nur den *Überlebenszeitraum* (typisch 5 Jahre post-termination für UK/US, „unbefristet" für DE Betriebsgeheimnisse) isolieren. | Folgekarte `t_employment_confidentiality_survival_baseline` (vorgeschlagen), die *sowohl* die DE- (BGB § 622 Abs. 6) als auch die UK/US-Seite (typische 5-Jahres-Erweiterung) zusammenführt. |
| `employment_working_hours` | DE-verankert durch das Arbeitszeitgesetz (ArbZG, max. 8 h/Tag, 48 h/Woche im Durchschnitt) + BGB § 611a (Arbeitsvertrag). UK-Komparator: Working Time Regulations 1998 (WTR 1998, max. 48 h/Woche, individuelle Opt-out-Möglichkeit). Der DE-Anker (ArbZG) ist die *load-bearing*; der UK-Komparator ist eine sinnvolle Sekundärquelle. | `playbook/baselines/employment-de/` in einer Folgekarte `t_employment_working_hours_baseline`, die *sowohl* die DE- (ArbZG) als auch die UK-Seite (WTR 1998) zusammenführt. |

## Entscheidungs-Log

Die „5 Baselines oder 3 + GAP.md"-Hedge im Karteibody existiert,
weil öffentlich-quellliche DE-Arbeitsvertrags-Vorlagen
*zahlreich* sind (IHK, Handwerkskammern, DGB, Ver.di, Big-4
Kanzleien), aber die *statutarische Anker-Struktur* im
deutschen Arbeitsrecht so dicht ist, dass eine
*saubere Einzelquelle-pro-Klausel*-Zuordnung mit nur
*Bundesgesetzestexten* die Quellenstreuung auf einen einzigen
Host (gesetze-im-internet.de) kollabieren lassen würde.

Die in dieser Karte gewählte Mischung aus 4 ×
gesetze-im-internet.de (für 4 unterschiedliche
Bundesgesetzestexte) + 1 × ihk.de (für die
Modellvertrags-Komponente) erreicht das richtige Maß: vier
amtliche deutsche Bundesgesetze für die statutarische
Verankerung der vier zentralen Klauseltypen, plus ein
offizielles IHK-Muster für die praxisnahe
Modellvertrags-Komponente. Die 4 gesetze-im-internet.de-Treffer
sind 4 *unterschiedliche* Dokumente (BGB § 622, BGB § 611a,
BUrlG § 3, BGB § 626), die zufällig auf demselben Host
veröffentlicht sind — analog zur DE-DPA-Karten-Logik mit den
EUR-Lex-Treffern (Art. 28 DSGVO + Art. 33 DSGVO + EU SCCs).

Die Entscheidung ist daher: 5 Baselines jetzt ausliefern
(die „5 echte-öffentliche-Quelle"-Branch der Karten-Hedge), und
die verbleibenden 6 in einer kleinen Anzahl von Folgekarten
anlegen, die *paarweise* DE+UK abdecken (für die
UK-spezifischen Werte) oder *einzeln* DE-anchored sind (für
die DE-spezifischen Werte). Die 5-Baseline-Set hier
zusammen mit den 5-Baseline-EN-Set der Karte t_d23d222d
decken insgesamt 9 der 11 `employment_*`-Werte ab, wenn man
die 3 DE-only- und 3 UK-only-Überschneidungen herausrechnet.

## Was Helenas Review-Karte erwarten sollte

- 5 Baselines in diesem Verzeichnis parsen sauber und lösen
  auf Phase-5-`employment_*`-Enum-Werte auf (verifiziert:
  Pydantic-Schema + ClauseType-Enum).
- Die SOURCES.md liefert 5 unterschiedliche, zitierbare
  öffentliche Quellen (4 × gesetze-im-internet.de + 1 × ihk.de).
- Die 6 fehlenden `employment_*`-Werte sind in dieser Datei
  mit einer geplanten Folgekarte dokumentiert.
- Der Spotter kann, wenn er auf einen realen DE-Arbeitsvertrag
  gerichtet wird, mindestens eine dieser 5 Baselines abrufen
  und zitieren (Smoke-Test folgt, sobald die Eval-Set-Karte
  ausgeliefert wird).

## Was NICHT als „Lücke" zählt, die es wert ist, gemeldet zu werden

- Eine *längere* Kündigungsfrist als die § 622 BGB-Statutarik
  (z. B. 6 Monate für eine Führungskraft) ist keine Lücke; sie
  ist eine strenger-als-Baseline-Position und die Matrix soll
  sie akzeptieren.
- Eine *kürzere* Kündigungsfrist als die § 622-Statutarik ist
  nach § 622 Abs. 5 BGB unwirksam (mit Ausnahmen für Aushilfen
  und Kleinbetriebe) und eine Abweichung, die in der Matrix zu
  kennzeichnen ist, nicht eine Lücke in der Baseline.
- Eine *höhere* Vergütung als vereinbart ist keine Lücke; sie
  ist eine freiwillige Leistung des Arbeitgebers (sofern nicht
  betriebliche Übung einen Anspruch begründet).
- Eine *niedrigere* Vergütung als der gesetzliche Mindestlohn
  (MiLoG) ist eine Abweichung, die in der Matrix zu
  kennzeichnen ist, nicht eine Lücke in der Baseline.
- Eine § 626-Klausel, die die Sozialgerechtigkeits-Prüfung
  nach § 1 Abs. 2 KSchG ausblendet, ist eine *operative*
  Abweichung in der Klauselstruktur (Matrix-Verdikt „material"),
  nicht eine Lücke in der Baseline-Set.
- Ein *kürzerer* Mindesturlaub als 24 Werktage (BUrlG § 3) ist
  nach § 13 BUrlG nichtig und eine Abweichung, die in der
  Matrix zu kennzeichnen ist, nicht eine Lücke in der Baseline.
- Eine *Kontaktaufnahme-Beschränkung* (No-Poach) ohne jede
  Kompensation ist nach § 138 BGB unwirksam und eine
  Abweichung, die in der Matrix zu kennzeichnen ist, nicht eine
  Lücke in der Baseline.
- Die *eigentliche* Wettbewerbsverbots-Klausel mit
  Karenzentschädigung (§ 74 HGB) ist *nicht* in dieser
  Baseline abgedeckt, sondern gehört zu `employment_non_compete`
  (geplante Folgekarte); Helenas Review-Karte sollte eine
  Verwechslung zwischen Non-Solicitation und Non-Compete als
  strukturelle Abweichung markieren.
