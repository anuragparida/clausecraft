# 06 — UI Spec

> Pages, components, design tokens, user flows.

**Status:** stub. Uses the default stack: Vite + TS + React + Tailwind + shadcn (dark mode).

## Pages (proposed)

1. **Home / Upload** — contract type picker, language picker, counterparty context form, file dropzone
2. **Triage in progress** — live status of the pipeline (ingest → parse → classify → dev-spot → aggregate), with per-stage progress
3. **Deviation review (HITL)** — the main work surface. Table of flags with:
   - Clause reference + excerpt
   - Severity (color-coded: 0=green, 1=yellow, 2=orange, 3=red)
   - Counterparty matrix verdict (acceptable / material / unacceptable for this counterparty type)
   - Citation (playbook clause id + link to source)
   - Per-row actions: Approve / Reject / Edit severity / Add context
   - Filter by severity, by clause type, by status
4. **Redline output** — preview of the .docx (rendered as HTML for the demo), download button, summary memo
5. **Audit log** — full decision chain for a contract, exportable as PDF/JSON/CSV
6. **Playbook viewer** (admin) — browse the public-source baseline clauses, see provenance
7. **Eval dashboard** — run report for the latest eval, precision/recall/F1 per contract type

## Design tokens (default shadcn dark mode)

- Color: shadcn default dark palette
- Density: table-heavy (deviation review is the main work surface) — comfortable row height, sticky header, monospace for clause text
- Typography: Geist Sans for UI, Geist Mono for clause text and citations
- Empty states: every page has one. The app's first run will not have data.

## Key components (shadcn-based)

- `DataTable` — sort, filter, multi-select rows, bulk actions
- `SeverityBadge` — color-coded 0-3
- `CitationPopover` — click to see the full playbook clause + source URL
- `DiffViewer` — side-by-side original vs proposed (for redline preview)
- `CounterpartyMatrixCard` — shows the (clause_type × counterparty_type) → acceptable_range verdict
- `AuditLogTimeline` — vertical timeline of decisions with rationale

## User flows

- **Happy path:** Upload → fill context → Triage → Review → Generate redline → Download
- **Demo path:** Home has a "Try with sample NDA" button → preloads a known-bad NDA → Triage → Review → wow moment on the deviation table
- **Audit path:** From any contract, click "View audit log" → see the full decision chain → export

## Open questions for this doc

- Live .docx preview in the browser — render via mammoth.js (HTML conversion) or ship as a static download only? (My take: mammoth.js for v1, removes the "is it going to look right in Word?" anxiety.)
- Side-by-side diff viewer — is the comparison clause-by-clause or full-document? (My take: clause-by-clause. Full-document is a separate feature.)
- Mobile? Probably not for v1, but the layout should not break on tablet.
