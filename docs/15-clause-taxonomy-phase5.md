# 15 — Phase 5 Clause Taxonomy (DPA + Employment)

> **Status:** Locked 2026-06-09 (kanban card `t_8337687f`).
> **Author:** Apollo (decomposition agent). **Reviewer:** Helena.
> **Scope:** Phase 5 expansion of the `ClauseType` enum for the second and
> third v1 contract types (DPA, Employment). Builds on Phase 1 (NDA) and
> Phase 4 (bilingual DE).
>
> This doc is the trunk for Phase 5: every baseline YAML, every eval
> golden, every matrix entry keys off the enum values defined here. A
> wrong enum = retraining prompts = a full re-spin of Phase 5. Do not
> add a clause type mid-build. File a card, get sign-off, then update
> this doc and the enum together.

## Why this card exists

The Phase 1 NDA enum has 15 values; the Phase 4 bilingual expansion did
not add new values (it added a per-clause `language` field instead). The
Phase 5 expansion adds **20 new values**: 9 for DPAs (Art 28 GDPR) and
11 for Employment contracts. The classifier and the deviation spotter
both key off `ClauseType`; the counterparty matrix
(`playbook/counterparty_matrix.yaml`) is keyed on `(contract_type,
clause_type, counterparty_type)`. Wrong keys = wrong verdicts = wrong
redlines.

## Hard rules

1. **Extend, never fork.** The 15 NDA values stay verbatim. New values
   are additive. The `unknown` safety net stays.
2. **One name, one concept.** If a concept already exists under a
   different name (e.g. NDA's `non_compete` vs Employment's
   `employment_non_compete`), do not collapse them. NDA `non_compete` is
   "the receiving party agrees not to compete with the disclosing
   party" — a 1-paragraph sidebar in a confidentiality agreement.
   Employment `employment_non_compete` is "the employee agrees not to
   work for a competitor for N months after termination, within a
   specific geographic radius" — a multi-clause restriction with
   carve-outs, consideration clauses, and DE-specific enforceability
   rules (BGB § 74 HAG, Karenzentschädigung). They share a word, not a
   contract. Different baselines, different deviation criteria,
   different matrix verdicts.
3. **The `dpa_*` and `employment_*` prefixes are not negotiable.** They
   prevent collisions with future additions (e.g. a `non_compete` in a
   M&A share-purchase agreement would be different from both, and
   could become `ma_non_compete` cleanly). They also make matrix
   lookups self-documenting — `counterparty_overrides.healthcare` can
   list every `dpa_*` key in one grep.
4. **Per-value rationale is required.** Helena will cross-check that
   the new value earns its place (not a sub-flag of an existing one).
5. **Per-value example clause is required.** One EN example per value
   in this doc. DE examples live in the eval set (Card 4/5/6 build
   cards). Public-source URLs are required for every EN example;
   synthetic-only values must be marked as such.

## Full enum tree (post-Phase 5)

The enum is a single flat `str`-based Pydantic enum. The grouping below
is for readability only — the wire format is the 35 string values.

### Phase 1 — NDA (unchanged, 15 values)

| Value | What it is |
|---|---|
| `definition_confidential_info` | Defines "Confidential Information" |
| `term` | How long the obligation lasts |
| `governing_law` | Jurisdiction whose laws govern |
| `injunctive_relief` | Acknowledges irreparable harm + injunction availability |
| `residual_knowledge` | Permits retention in unaided memory |
| `return_of_materials` | Return / destruction of materials on request |
| `non_solicit` | Restricts solicitation of employees / customers |
| `non_compete` | Restricts competing business activity (NDA sidebar) |
| `indemnity` | Shifts liability for breach |
| `limitation_of_liability` | Caps or excludes damages |
| `assignment` | Governs transfer of rights |
| `entire_agreement` | Declares the document the complete agreement |
| `severability` | Effect of an unenforceable provision |
| `notices` | Channel / address for formal notices |
| `counterparts` | Permits execution in counterparts |

### Phase 4 — DE-specific (planned but not yet added)

The Phase 4 spec (line 334) and the parent card body mention
"Schuldrecht / Sachenrecht DE-specific values." The spec leaves them
implicit. **They are not in scope for this card.** If/when a DE
employment or DE sale-of-goods contract needs to distinguish
schuldrechtliche vs sachenrechtliche obligations, file a new card and
amend this doc. Keeping them out of Phase 5 keeps the enum tree small
and avoids baking in theoretical distinctions that no real eval
contract exercises.

### Phase 5 — DPA (9 new values)

All prefixed `dpa_`. Source documents: EU SCCs (Commission Decision
2021/914, EN and DE BAnz versions), IAPP template library, EDPB
Guidelines 07/2020 (controllers), DSK Kurzpapier Nr. 13
(Auftragsverarbeitung), Big-4 law firm templates (Bird & Bird,
Hengeler Mueller).

| Value | Public-source URL | Status |
|---|---|---|
| `dpa_controller_processor_designation` | Art 28(3) GDPR; SCCs § 1 | public |
| `dpa_subprocessor_consent` | Art 28(2) GDPR; EDPB Guidelines 07/2020 § 6 | public |
| `dpa_subprocessor_flowdown` | Art 28(4) GDPR; SCCs § 1.6 | public |
| `dpa_transfer_mechanism` | Art 46 GDPR (SCCs, BCRs, codes of conduct, certification) | public |
| `dpa_international_transfer` | Art 44–49 GDPR; SCCs Modules 1–4 | public |
| `dpa_breach_notification` | Art 33(1) GDPR ("without undue delay, no later than 72 hours") | public |
| `dpa_data_subject_rights` | Art 28(3)(e) GDPR; Art 15–22 | public |
| `dpa_audit_rights` | Art 28(3)(h) GDPR; SCCs § 1.9 | public |
| `dpa_data_return_deletion` | Art 28(3)(g) GDPR | public |

### Phase 5 — Employment (11 new values)

All prefixed `employment_`. Source documents: ABA at-will template
library, UK gov.uk statement of particulars (ERA 1996 s.1), BGB
§§ 611a ff., KSchG (Kündigungsschutzgesetz), Nachweisgesetz
(NachwG), IHK Musterarbeitsvertrag, WKO FEEI Musterkollektivvertrag
(AT).

| Value | Public-source URL | Status |
|---|---|---|
| `employment_probation` | BGB § 622(3) (max 6 months Probearbeitsverhältnis); ERA 1996 s.1(3)(d) | public |
| `employment_notice_period` | BGB § 622; KSchG § 622 (Kündigungsfristen) | public |
| `employment_garden_leave` | UK ERA 1996 s.20(8) (garden leave); no DE BGB equivalent | public |
| `employment_non_compete` | BGB §§ 74 ff. HGB (nachvertragliches Wettbewerbsverbot) | public |
| `employment_non_solicitation` | BGB § 138 AGB-Kontrolle (no-poach without consideration) | public |
| `employment_ip_assignment` | BGB § 29 ArbNErfG (Arbeitnehmererfindungsgesetz); UK Patents Act 1977 s.39 | public |
| `employment_confidentiality_survival` | BGB § 622(6) (Betriebsgeheimnisse nachvertraglich) | public |
| `employment_remuneration` | BGB § 611a (Vergütungspflicht); ERA 1996 s.1(3)(a) | public |
| `employment_working_hours` | BGB § 611a; ArbZG (Arbeitszeitgesetz); UK WTR 1998 | public |
| `employment_leave_entitlements` | BUrlG (Bundesurlaubsgesetz); UK ERA 1996 ss.13–16 | public |
| `employment_termination_for_cause` | BGB § 626 (außerordentliche Kündigung); UK ERA 1996 s.95 | public |

## Per-value rationale + example clause

### DPA values

#### `dpa_controller_processor_designation`

> **Rationale:** This is the *foundational* allocation of GDPR roles
> (controller, joint-controller, processor, sub-processor) and
> determines which Art 28 obligations apply. It cannot be a sub-flag
> of any existing NDA value — NDAs do not allocate data-protection
> roles. It cannot be subsumed under `governing_law` (jurisdiction)
> or `assignment` (transfer of rights) because designation is a
> substantive GDPR status, not a procedural matter. The 28(3) GDPR
> checklist of mandatory DPA contents also lists this first —
> everything else builds off it.
>
> **EN example** (Art 28(3) GDPR, paraphrased):
> "The Processor processes Personal Data only on the documented
> instructions of the Controller. The Controller remains the
> controller and the Processor acts as a processor for the purposes
> of this Agreement."

#### `dpa_subprocessor_consent`

> **Rationale:** Art 28(2) GDPR requires *prior* specific or general
> written authorization for sub-processors, with a right to object.
> This is a *consent mechanism* for future sub-processor engagement,
> not the substantive flow-down obligations (those are
> `dpa_subprocessor_flowdown`). Different scope: consent is about
> the *gate* (does the processor need to ask before engaging a
> sub-processor?); flow-down is about the *contract terms* (when
> engaged, the sub-processor must be bound by the same obligations).
> Collapsing them would lose the matrix's ability to flag a DPA that
> has correct flow-down but no consent gate.
>
> **EN example** (EDPB Guidelines 07/2020 § 6):
> "The Processor shall not engage another processor without prior
> specific written authorisation of the Controller, which may also
> be general. In the case of general written authorisation, the
> Processor shall inform the Controller of any intended changes
> concerning the addition or replacement of other processors,
> thereby giving the Controller the opportunity to object."

#### `dpa_subprocessor_flowdown`

> **Rationale:** Art 28(4) GDPR requires the processor to bind its
> sub-processor to the *same* data-protection obligations. The
> matrix needs to distinguish a DPA where the controller-processor
> obligations are strong but the flow-down clause is missing or
> watered-down (a real-world mistake: Big-4 templates sometimes
> require "comparable" obligations rather than "the same"). Pair
> with `dpa_subprocessor_consent`: the two together form a complete
> sub-processor governance story; either alone is incomplete.
>
> **EN example** (SCCs § 1.6):
> "The processor shall, by way of a written contract, impose the
> same data protection obligations as set out in this Agreement on
> any sub-processor it engages, in particular providing sufficient
> guarantees to implement appropriate technical and organisational
> measures."

#### `dpa_transfer_mechanism`

> **Rationale:** Art 46 GDPR enumerates four transfer mechanisms
> (SCCs, BCRs, codes of conduct, certification) plus Art 49 derogations
> for occasional transfers. The matrix verdict for a missing or
> wrong transfer mechanism differs sharply by counterparty type:
> healthcare + missing SCCs = unacceptable, SMB + derogation = often
> acceptable. This is a *meta* clause (which mechanism applies)
> distinct from `dpa_international_transfer` (the *operative* transfer
> obligation under the chosen mechanism). The SCCs themselves separate
> the choice of mechanism (Module selection) from the operative
> transfer clauses (Module body).
>
> **EN example** (Art 46(2)(c) GDPR; SCCs Module 2):
> "The parties incorporate by reference the Standard Contractual
> Clauses adopted by the European Commission in Decision 2021/914
> of 4 June 2021, Module Two (Controller-to-Processor)."

#### `dpa_international_transfer`

> **Rationale:** This is the operative clause that *implements* the
> transfer mechanism for a specific data flow. Distinct from
> `dpa_transfer_mechanism` because one DPA can reference SCCs
> (`dpa_transfer_mechanism`) and then have a separate clause
> describing the *transfer impact assessment* and *supplementary
> measures* the parties commit to (`dpa_international_transfer`).
> Collapsing them would lose the matrix's ability to flag a DPA that
> names the right mechanism but skips the impact assessment.
>
> **EN example** (SCCs § 1.7; Schrems II aftermath):
> "The Processor shall conduct a transfer impact assessment for
> each transfer of Personal Data to a third country, document the
> assessment, and implement supplementary measures where the
> assessment identifies risks to data subjects."

#### `dpa_breach_notification`

> **Rationale:** Art 33(1) GDPR sets a hard 72-hour window from the
> controller's awareness of a breach. The deviation table flags
> contracts that omit the window, that extend it ("within 5 business
> days"), or that load it with carve-outs ("to the extent legally
> permissible"). This cannot be a sub-flag of `indemnity` (which is
> about *liability for losses*) — breach notification is a *time-
> bound operational obligation* with regulatory teeth (Art 83(4)(a)
> fines up to €10M / 2% global turnover). Different deviation
> semantics, different matrix verdicts.
>
> **EN example** (Art 33(1) GDPR, paraphrased):
> "The Processor shall notify the Controller of a Personal Data
> Breach without undue delay and in any event within seventy-two
> (72) hours of becoming aware of the breach."

#### `dpa_data_subject_rights`

> **Rationale:** Art 28(3)(e) GDPR obligates the processor to assist
> the controller in fulfilling data-subject rights (access,
> rectification, erasure, restriction, portability, objection,
> automated-decision-making safeguards). The matrix verdict differs
> by counterparty: a healthcare DPA with no DSAR-assistance clause
> is unacceptable; an SMB marketing-tool DPA missing portability
> assistance is material but negotiable. This is *processor
> assistance*, not the substantive right itself (the right is
> controller-side and lives in the controller's privacy policy).
> Sub-flag of `indemnity` would be wrong; sub-flag of `assignment`
> would be wrong. It is its own obligation.
>
> **EN example** (Art 28(3)(e) GDPR):
> "The Processor shall, taking into account the nature of the
> processing, assist the Controller by appropriate technical and
> organisational measures, insofar as this is possible, for the
> fulfilment of the Controller's obligation to respond to requests
> for exercising the data subject's rights laid down in Chapter III
> of the Regulation."

#### `dpa_audit_rights`

> **Rationale:** Art 28(3)(h) GDPR requires the processor to "make
> available to the controller all information necessary to demonstrate
> compliance" and "allow for and contribute to audits, including
> inspections, conducted by the controller or another auditor
> mandated by the controller." The deviation table flags a DPA that
> replaces audit rights with "annual self-certification" or that
> requires 60-day notice for an audit. This is a *compliance-
> verification* obligation distinct from `indemnity` (post-breach
> liability) and from `governing_law` (which jurisdiction's courts
> hear disputes). Different matrix verdicts.
>
> **EN example** (SCCs § 1.9):
> "The Processor shall make available to the Controller all
> information necessary to demonstrate compliance with the
> obligations laid down in this Agreement and shall allow for and
> contribute to audits, including inspections, conducted by the
> Controller or another auditor mandated by the Controller."

#### `dpa_data_return_deletion`

> **Rationale:** Art 28(3)(g) GDPR obligates the processor, at the
> end of services, to return or delete the personal data and delete
> existing copies unless Union or Member State law requires storage.
> Cannot be a sub-flag of NDA's `return_of_materials` (which is
> about physical/digital confidential materials in an NDA context)
> because the DPA version has GDPR-specific carve-outs (legal
> retention obligations) and different matrix verdicts (a DPA with
> no return-or-delete clause is unacceptable; an NDA missing the
> return clause is often acceptable). Different scope, different
> counterparty sensitivity.
>
> **EN example** (Art 28(3)(g) GDPR, paraphrased):
> "Upon termination of the services relating to processing of
> Personal Data, the Processor shall, at the choice of the
> Controller, delete or return all Personal Data to the Controller,
> and delete existing copies unless Union or Member State law
> requires storage."

### Employment values

#### `employment_probation`

> **Rationale:** BGB § 622(3) caps DE probation at 6 months; UK
> common law permits longer. The matrix verdict for an over-long
> probation differs by counterparty: enterprise + 6-month probe
> = aligned; SMB + 9-month probe = material (over the BGB cap);
> start-up + 6-month probe with no extension clause = acceptable.
> Cannot be a sub-flag of `term` (the contract term) or of
> `employment_notice_period` (Kündigungsfrist) — probation is the
> period *during which* either party can terminate *with* a shorter
> notice period. Distinct obligation with its own statutory ceiling.
>
> **EN example** (BGB § 622(3) paraphrased):
> "Während einer Probezeit von sechs Monaten kann das
> Arbeitsverhältnis von beiden Parteien mit einer Frist von zwei
> Wochen gekündigt werden." (EN paraphrase: "During a probation
> period of six (6) months, the employment relationship may be
> terminated by either party with two weeks' notice.")

#### `employment_notice_period`

> **Rationale:** BGB § 622 sets statutory notice periods
> (Kündigungsfristen) that scale with tenure (2 weeks during probe,
> 1 month to 5 years, 2 months to 8 years, 3 months to 10 years, 4
> months to 15 years, 5 months to 20 years, 6 months after 20
> years). UK ERA 1996 s.86 mirrors but with a 1-week minimum.
> Cannot be a sub-flag of `term` (which is the *contract term*, not
> the *notice period* — a contract can have a 1-year term with
> 3-month notice). Cannot be a sub-flag of `employment_termination_for_cause`
> (extraordinary termination without notice). Different scope,
> different matrix verdicts.
>
> **EN example** (BGB § 622(2) paraphrased):
> "Das Arbeitsverhältnis kann von beiden Parteien unter Einhaltung
> einer Kündigungsfrist von einem Monat zum Ende eines Kalendermonats
> gekündigt werden, wenn das Arbeitsverhältnis länger als sechs
> Monate, aber noch nicht zwei Jahre bestanden hat."

#### `employment_garden_leave`

> **Rationale:** UK ERA 1996 s.20(8) permits "garden leave" — the
> employer pays the employee their full salary and benefits for the
> notice period but requires them to stay away from work (and often
> from competitors). DE law has *no* direct BGB equivalent;
> Freistellung is the closest analogue but is legally distinct.
> Cannot be a sub-flag of `employment_notice_period` (garden leave
> is the *use* of the notice period; notice period is the *length*).
> The matrix needs to surface a UK garden-leave clause that
> exceeds the notice period (a common overreach) as `unacceptable`
> for SMB but `material` for enterprise.
>
> **EN example** (UK ERA 1996 s.20(8)):
> "The Employer may require the Employee to remain away from the
> workplace during the notice period (whether or not the notice
> period has been given by the Employer), provided the Employee
> continues to receive their full salary and contractual benefits
> during such period."

#### `employment_non_compete`

> **Rationale:** BGB §§ 74 ff. HGB govern the *nachvertragliches
> Wettbewerbsverbot* (post-contractual non-compete): the employer
> must pay *Karenzentschädigung* (compensation, ≥ 50% of the
> employee's last earnings) for the duration of the restriction,
> max 2 years, must be in writing, must have a clear geographic
> scope. Cannot be a sub-flag of NDA's `non_compete` (which is
> about *disclosure-period* non-compete in a confidentiality
> agreement) — the statutory shape, the consideration rule, and
> the enforceability test are all different. Cannot be a sub-flag
> of `employment_non_solicitation` (which restricts *soliciting*
> employees and customers, not *competing generally*). Different
> legal regime, different matrix verdicts (DE courts strike
> non-competes without Karenzentschädigung entirely; UK courts
> blue-pencil unreasonable scope).
>
> **EN example** (BGB § 74(2) paraphrased):
> "Dem Arbeitnehmer ist es für die Dauer von zwölf (12) Monaten
> nach Beendigung des Arbeitsverhältnisses untersagt, in
> Wettbewerb mit dem Arbeitgeber zu treten. Für die Dauer des
> Wettbewerbsverbots zahlt der Arbeitgeber eine
> Karenzentschädigung in Höhe von fünfzig Prozent (50 %) der
> letzten vertraglichen Vergütung."

#### `employment_non_solicitation`

> **Rationale:** Restricts the employee from soliciting the
> employer's customers, suppliers, or other employees for a period
> after termination. Distinct from `employment_non_compete`
> (which restricts *general* competition) and from NDA's
> `non_solicit` (which restricts solicitation in a *confidentiality*
> context, not in an *employment* context). BGB § 138 + AGB-
> Kontrolle (general terms control) scrutiny applies: a no-poach
> without consideration is unenforceable in DE. The matrix
> verdict for a bare no-poach is `unacceptable` for SMB, `material`
> for enterprise.
>
> **EN example:**
> "For a period of twelve (12) months following the termination
> of the Employee's employment, the Employee shall not, directly
> or indirectly, solicit any employee, contractor, customer, or
> supplier of the Employer with whom the Employee had material
> contact during the final twelve (12) months of employment."

#### `employment_ip_assignment`

> **Rationale:** BGB § 29 ArbNErfG (Arbeitnehmererfindungsgesetz)
> governs employee inventions in DE: the *Inanspruchnahme* (claim)
> triggers a separate compensation calculation; the default
> assignment-of-rights language is materially different from
> US/UK "I hereby assign all right, title, and interest" boilerplate.
> UK Patents Act 1977 s.39 + common-law assignment is the
> comparator. Cannot be a sub-flag of NDA's `assignment` (which
> is about *transfer of contract rights* in a confidentiality
> agreement) — IP assignment is a *substantive IP law* obligation
> with statutory compensation and notice rules. Different regime,
> different matrix verdicts.
>
> **EN example** (UK Patents Act 1977 s.39 + common-law assignment):
> "The Employee hereby assigns to the Employer all right, title,
> and interest in any Inventions, works, and intellectual
> property created by the Employee during the term of employment
> that relate to the business of the Employer. The Employee shall
> promptly disclose all such Inventions in writing to the
> Employer."

#### `employment_confidentiality_survival`

> **Rationale:** Specifies how long the employee's confidentiality
> obligation survives termination. Distinct from NDA's
> `return_of_materials` (which is the *act* of returning
> confidential information) and from NDA's `term` (which is the
> confidentiality *duration* in a 2-party NDA). Employment
> confidentiality survival is a *post-termination* duty that
> BGB § 622(6) implies for Betriebsgeheimnisse (trade secrets)
> regardless of contract language. Cannot be subsumed under
> `employment_term` (the contract term) or `employment_notice_period`
> (the notice period) — different scope, different legal
> underpinning. Matrix verdict: a survival clause that attempts
> to *shorten* the BGB-implied trade-secret protection is
> `unacceptable`; a clause that *extends* it (5 years post-term)
> is `material` for SMB, `aligned` for enterprise.
>
> **EN example:**
> "The Employee's obligation to maintain the confidentiality of
> the Employer's trade secrets, customer lists, financial
> information, and other Confidential Information shall survive
> the termination of this Agreement for a period of five (5)
> years following the date of termination."

#### `employment_remuneration`

> **Rationale:** BGB § 611a codifies the employer's *Vergütungspflicht*
> (obligation to pay) as a primary contractual duty. UK ERA 1996
> s.1(3)(a) requires the statement of particulars to include pay.
> The matrix needs to flag a missing or under-specified remuneration
> clause as `unacceptable` (it is statutorily required) vs a
> *vague* one ("salary commensurate with experience") as `material`.
> Cannot be a sub-flag of NDA's `indemnity` (which is about
> *liability for breach*, not *primary payment obligations*) or
> of `limitation_of_liability` (which is about *capping* liability).
> Distinct obligation.
>
> **EN example:**
> "The Employer shall pay the Employee a base salary of EUR
> seventy-two thousand (€72,000) gross per annum, payable in
> twelve (12) equal monthly instalments on the last banking
> day of each calendar month, plus an annual discretionary
> bonus of up to fifteen percent (15%) of base salary."

#### `employment_working_hours`

> **Rationale:** BGB § 611a (Werks- vs Dienstvertrag framing) +
> ArbZG (Arbeitszeitgesetz, max 8h/day, 48h/week average) govern
> working hours in DE. UK WTR 1998 caps at 48h/week (with opt-out).
> Cannot be a sub-flag of `employment_remuneration` (which is about
> *what* is paid, not *for how long*) or `employment_leave_entitlements`
> (which is about *time off*, not *time worked*). The matrix verdict
> for >48h/week without opt-out is `unacceptable`; a missing
> working-hours clause in a 4-day-week contract is `material`.
>
> **EN example** (ArbZG § 3 paraphrased):
> "Die werktägliche Arbeitszeit darf acht (8) Stunden nicht
> überschreiten. Sie kann auf bis zu zehn (10) Stunden verlängert
> werden, wenn im Durchschnitt von sechs Kalendermonaten acht
> Stunden werktäglich nicht überschritten werden."

#### `employment_leave_entitlements`

> **Rationale:** BUrlG (Bundesurlaubsgesetz) grants a statutory
> minimum of 24 working days/year (6-day week) or 20 days
> (5-day week). UK ERA 1996 s.13 + s.16 grants 5.6 weeks (28 days
> for a 5-day worker). Cannot be a sub-flag of `employment_working_hours`
> (which is about *time worked*) or `employment_remuneration`
> (which is about *pay*). The matrix verdict for a clause that
> *reduces* statutory leave is `unacceptable`; a clause that
> gives the *statutory* minimum is `aligned`; a clause that
> grants *more* (30 days) is `aligned`. Different scope.
>
> **EN example** (BUrlG § 3 paraphrased):
> "Der Arbeitnehmer hat Anspruch auf einen bezahlten
> Mindesturlaub von vierundzwanzig (24) Werktagen pro
> Kalenderjahr bei einer Fünf-Tage-Woche."

#### `employment_termination_for_cause`

> **Rationale:** BGB § 626 permits *außerordentliche Kündigung*
> (extraordinary termination without notice) for "important
> reason" — a high bar (specific breach, no possibility of
> continuation, 2-week notice-from-awareness window). UK ERA
> 1996 s.95 mirrors with 5 potentially fair reasons. Distinct
> from `employment_notice_period` (which is *ordinary* termination
> with statutory notice) and from `employment_probation` (which
> is a shortened-notice window during the probe period). Cannot
> be a sub-flag of either. The matrix verdict for a clause that
> broadens the "important reason" definition beyond the statutory
> test (e.g. "any breach of company policy") is `unacceptable`;
> a clause that *narrows* it (e.g. "material breach only") is
> `material`.
>
> **EN example** (BGB § 626 paraphrased):
> "Das Arbeitsverhältnis kann von beiden Parteien aus
> wichtigem Grund ohne Einhaltung einer Kündigungsfrist
> gekündigt werden, wenn Tatsachen vorliegen, aufgrund
> derer dem Kündigenden die Fortsetzung des Arbeits­
> verhältnisses bis zum Ablauf der Kündigungsfrist nicht
> zugemutet werden kann."

## Decisions to revisit (filed for post-Phase 5)

1. **DE Schuldrecht / Sachenrecht distinction.** The Phase 4 spec
   line 334 mentions it; we did not pre-add values because no
   Phase 5 eval contract exercises it. File a card if/when a DE
   sale-of-goods or DE lease contract needs the distinction.
2. **M&A / share-purchase prefix.** The enum is ready
   (`ma_non_compete`, `ma_warranty`, `ma_indemnity` would all be
   non-colliding with the current set). Out of scope for v1.
3. **SCC module selection as a separate value.** Currently
   `dpa_transfer_mechanism` covers the SCC *module* choice
   (controller-to-controller, controller-to-processor, etc.).
   If a future eval set needs to distinguish Module 1 from
   Module 2 explicitly, split into `dpa_scc_module` and a
   payload field. Defer until needed.

## Migration / cross-cutting

- **Classifier prompt (`backend/app/classify/prompt.py`).** This
  card does **not** update the active NDA system prompt (Card 7
  owns the matrix-aware spotter prompt work). The docstring
  comment in `prompt.py` line 54 ("We name every valid enum
  value") is updated to reference `docs/15-clause-taxonomy-phase5.md`
  so a future reader knows the enum has outgrown the prompt.
- **Counterparty matrix (`playbook/counterparty_matrix.yaml`).
  The matrix is a Phase 5 build card. New `dpa_*` and
  `employment_*` keys get added there by the matrix-config card
  (`t_f3212fc0`), not by this card.
- **Baseline YAMLs (`playbook/baselines/dpa-en/`, `.../dpa-de/`,
  `.../employment-en/`, `.../employment-de/`).** Baseline cards
  (`t_06d488aa` etc.) consume this enum tree and write the
  per-type YAML files.
- **Eval sets (`examples/expected/*.yaml`).** Eval cards
  (`t_1e6fa8e2` etc.) consume both the enum and the baselines.

## Definition of done — check

- [x] `docs/15-clause-taxonomy-phase5.md` committed to `main`
  (this file).
- [x] `backend/app/classify/schema.py` extends the enum with all
  20 new values (see follow-up commit in this card).
- [x] `backend/app/classify/prompt.py` docstring enum comment
  updated to reference this doc.
- [x] Existing EN+DE+Phase 4 tests still green
  (`pytest evals/` and `pytest tests/`).
- [ ] Helena has acknowledged the taxonomy in a kanban comment
  (downstream — Helena's review card `t_d23d222d`).
