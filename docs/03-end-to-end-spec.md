# 03 — End-to-End Spec

> Full user journey, edge cases, failure modes, success criteria.

**Status:** stub.

## Primary user journey

1. User opens the app (local or deployed)
2. User selects contract type (NDA / DPA / Employment) — can also auto-detect
3. User uploads contract (PDF or DOCX)
4. User fills counterparty context: "I am a [vendor/buyer/employer/employee] contracting with a [SaaS enterprise / SMB / public-sector / healthcare] in [DE / US / EU / UK]"
5. User clicks "Triage"
6. System runs: ingest → parse → classify → playbook lookup → deviation spot → aggregate
7. System pauses at HITL checkpoint, shows deviation table
8. User reviews each flag: Approve / Reject / Edit severity / Add context
9. User clicks "Generate redline"
10. System runs: redline drafter (accepted flags only) → tracked-changes .docx + summary memo
11. User downloads .docx + reads summary memo
12. Audit trail is available for export at any point

## Edge cases

- Scanned PDF (image, no text layer) — needs vision model fallback or OCR
- Mixed-language contract (EN contract with DE governing-law clause)
- Contract in unsupported language (FR, IT) — graceful error, don't crash
- Very large contract (100+ pages) — chunked processing, progress indicator
- Very short / malformed contract — refuse gracefully, don't invent clauses
- No playbook match for a clause type — log it, surface to user, do not silently invent a baseline
- LLM returns malformed structured output — Pydantic validation, retry with reflection, max 2 retries then escalate to user

## Failure modes

- LLM API down — queue the job, show "queued" state, retry on backoff
- Langfuse unreachable — system should still run; log locally, sync later
- Postgres unreachable — fail loud; no silent drops

## Success criteria (v1)

- All 3 contract types (NDA, DPA, Employment) process end-to-end without human intervention up to the HITL checkpoint
- HITL is a real, pauseable, reviewable step — not a cosmetic button
- Output .docx opens cleanly in Word and LibreOffice, tracked changes are visible
- Summary memo is 1 page, plain language, references the deviation table
- Audit log is exportable and complete (every decision has a row)

## Open questions for this doc

- Is there a "demo mode" where a known-bad contract is preloaded for live demos? (Probably yes — one-click demo button.)
- Is the counterparty context form step mandatory, or skippable with a default? (My take: required, with sane defaults for the demo contract type.)
