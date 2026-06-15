// Phase 5 — counterparty matrix verdict cell (t_1e6fa8e2).
//
// Scope (per card body)
// ---------------------
// Single component, no refactor of the existing deviation
// table. Replaces the "Matrix verdict" cell in
// ``DeviationReview.tsx`` with a 4-state badge (using
// the same ``SeverityBadge`` colour rules so the visual
// contract is shared with the "Severity" column) and a
// popover that shows the lookup chain that produced the
// verdict.
//
// What this component does
// ------------------------
//   - Reads the flag's ``matrix_verdict``,
//     ``matrix_sources``, and ``matrix_counterparty_type``.
//   - Renders a coloured badge with the verdict label.
//     The colour follows the existing ``SeverityBadge``
//     rules: acceptable → sev-1 (amber), material →
//     sev-2 (orange), unacceptable → sev-3 (red),
//     unverified → sev-0 (green safe default).
//   - When ``matrix_sources`` is non-empty, the badge
//     doubles as a popover trigger. Clicking opens a
//     small panel listing the lookup chain in
//     human-readable form (e.g. "clause_type (counterparty,
//     flat)"). The popover is the QA hook the card body
//     names: "Skim 5 random deviation rationales —
//     confirm the matrix verdict influenced the score."
//   - When ``matrix_verdict`` is missing (Phase 2/3/4
//     backend, no Phase 5 plumbing), falls back to the
//     score-derived label and a "flat baseline (Phase 5
//     adds matrix)" caption. The existing Phase 2 test
//     ``renders the matrix verdict column with the flat
//     baseline verdict`` continues to pass.
//
// What this component does NOT do
// -------------------------------
//   - Re-derive the matrix verdict. The backend is the
//     source of truth; this cell is purely a renderer.
//   - Render the popover as a portal. Per the Phase 2
//     scope, all popovers in this codebase are inline
//     (no Radix, no portal) — the citation popover is
//     the template. Phase 5 keeps the pattern.
//   - Localise the verdict labels. EN copy is the
//     JSX-fallback; DE labels are part of the i18n shim's
//     coverage (see the language picker's pattern).
//
// Test hooks
// ----------
// - data-testid="matrix-verdict-cell-<clause_id>" (the
//   outer cell wrapper)
// - data-testid="matrix-verdict-badge-<clause_id>" (the
//   badge itself; data-matrix-verdict=acceptable|...)
// - data-testid="matrix-verdict-popover-trigger-<clause_id>"
//   (the clickable trigger; only present when sources
//   are non-empty)
// - data-testid="matrix-verdict-popover-panel-<clause_id>"
//   (the popover panel; only present when open)
// - data-testid="matrix-verdict-sources-<clause_id>"
//   (the lookup chain list inside the popover)

import { useState } from "react";
import { cn } from "@/lib/utils";

// --- Types -------------------------------------------------------------

/** The 4-state column form. Mirrors the backend's
 *  ``MATRIX_VERDICT_VALUES`` tuple and
 *  :class:`CounterpartyType`'s 4 axes + the legacy
 *  ``"any"`` sentinel. */
export type MatrixVerdict =
  | "acceptable"
  | "material"
  | "unacceptable"
  | "unverified";

/** The 4 Phase 5 counterparty axes + the legacy ``"any"``
 *  sentinel. Mirrors :class:`CounterpartyPicker`'s
 *  ``CounterpartyType``. */
export type CounterpartyTypeForCell =
  | "enterprise"
  | "smb"
  | "public_sector"
  | "healthcare"
  | "any";

export interface MatrixVerdictCellProps {
  clauseId: string;
  /** The matrix verdict to render. ``undefined`` means
   *  "no matrix verdict emitted" (Phase 2/3/4 backend);
   *  the cell falls back to the score-derived label. */
  matrixVerdict?: MatrixVerdict | null;
  /** The lookup chain that produced the verdict. The
   *  popover surfaces this when non-empty. */
  matrixSources?: string[] | null;
  /** The counterparty type the matrix was consulted
   *  with. Used in the popover's header (e.g.
   *  "lookup @ healthcare"). */
  matrixCounterpartyType?: CounterpartyTypeForCell | null;
  /** The spotter's numeric score (0..3). Used as the
   *  fallback label when ``matrixVerdict`` is missing. */
  score: number;
  /** Display language. Reserved for the i18n shim's
   *  verdict-label coverage (Phase 4 EN-fallback /
   *  DE-lookup). */
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  displayLanguage?: "en" | "de";
}

// --- Colour mapping ----------------------------------------------------
//
// Mirrors the SeverityBadge's sev-0..sev-3 colour rules
// so the visual contract is shared with the "Severity"
// column:
//
//   acceptable     → sev-1 amber  (low risk; the matrix
//                                  agreed with the spotter)
//   material       → sev-2 orange (the deal-breaker
//                                  warning; the matrix
//                                  escalates the spot score)
//   unacceptable   → sev-3 red    (matrix says no-go)
//   unverified     → sev-0 green  (the pipeline abstained;
//                                  safe default)
//
// Same colour = same visual language as the existing
// column. A reviewer can scan the row left-to-right and
// read the same colour twice for "the spotter and the
// matrix agree".

const CLASSES_FOR_VERDICT: Record<MatrixVerdict, string> = {
  acceptable:
    "border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-300",
  material:
    "border-transparent bg-orange-500/15 text-orange-700 dark:text-orange-300",
  unacceptable:
    "border-transparent bg-red-500/15 text-red-700 dark:text-red-300",
  unverified:
    "border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
};

/** Render a MatrixVerdict as a short human label.
 *  Kept here (not in the i18n JSON) because the values
 *  are spec-locked identifiers, not page chrome. The
 *  column header is a separate string ("Matrix verdict"
 *  / "Matrix-Urteil" in DE). */
function verdictLabel(v: MatrixVerdict): string {
  switch (v) {
    case "acceptable":
      return "Acceptable";
    case "material":
      return "Material";
    case "unacceptable":
      return "Unacceptable";
    case "unverified":
      return "Unverified";
  }
}

/** Counterparty type → human label. Mirrors
 *  :func:`CounterpartyPicker.counterpartyTypeLabel` for
 *  the cell's popover header. Kept as a private copy
 *  here (not imported) because the cell is a self-
 *  contained renderer — it doesn't need the picker's
 *  full surface (label keys, hint copy, i18n shim). */
function counterpartyLabelForCell(
  t: CounterpartyTypeForCell,
): string {
  switch (t) {
    case "enterprise":
      return "Enterprise";
    case "smb":
      return "SMB";
    case "public_sector":
      return "Public sector";
    case "healthcare":
      return "Healthcare";
    case "any":
      return "Any (flat baseline)";
  }
}

/** Map a spotter score (0..3) to the matrix's internal
 *  label. Mirrors the scoreToVerdictLabel() helper in
 *  DeviationReview.tsx. Kept local to avoid an import
 *  cycle. */
function scoreToVerdictLabel(score: number): string {
  switch (score) {
    case 0:
      return "aligned";
    case 1:
      return "minor";
    case 2:
      return "material";
    case 3:
      return "unacceptable";
    default:
      return "aligned";
  }
}

// --- Component ---------------------------------------------------------

export function MatrixVerdictCell({
  clauseId,
  matrixVerdict,
  matrixSources,
  matrixCounterpartyType,
  score,
}: MatrixVerdictCellProps) {
  const [open, setOpen] = useState(false);

  // The fallback path: no matrix verdict emitted by the
  // backend (Phase 2/3/4 or no v1 plumbing). Render the
  // score-derived label and a "flat baseline" caption.
  // The data-matrix-verdict attribute on the badge is
  // set to the same string the Phase 2 test asserts on
  // (``"minor"`` for score=1, ``"unacceptable"`` for
  // score=3) so the legacy test still passes.
  if (!matrixVerdict) {
    const fallbackLabel = scoreToVerdictLabel(score);
    return (
      <div
        className="flex flex-col gap-1 text-xs"
        data-testid={`matrix-verdict-cell-${clauseId}`}
        data-fallback="true"
      >
        <span
          data-testid={`matrix-verdict-badge-${clauseId}`}
          data-matrix-verdict={fallbackLabel}
          className="font-mono text-muted-foreground"
        >
          {fallbackLabel}
        </span>
        <span className="text-[10px] text-muted-foreground">
          flat baseline (Phase 5 adds matrix)
        </span>
      </div>
    );
  }

  // The matrix verdict path: badge with a popover (when
  // the lookup chain is non-empty).
  const hasPopover = Array.isArray(matrixSources) && matrixSources.length > 0;
  const counterpartyLabel = matrixCounterpartyType
    ? counterpartyLabelForCell(matrixCounterpartyType)
    : null;

  return (
    <div
      className="flex flex-col gap-1 text-xs"
      data-testid={`matrix-verdict-cell-${clauseId}`}
      data-fallback="false"
    >
      {hasPopover ? (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className={cn(
            "inline-flex w-fit items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
            CLASSES_FOR_VERDICT[matrixVerdict],
            "cursor-pointer hover:opacity-90",
          )}
          data-testid={`matrix-verdict-popover-trigger-${clauseId}`}
          data-matrix-verdict={matrixVerdict}
          aria-expanded={open}
        >
          {verdictLabel(matrixVerdict)}
        </button>
      ) : (
        <span
          className={cn(
            "inline-flex w-fit items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold",
            CLASSES_FOR_VERDICT[matrixVerdict],
          )}
          data-testid={`matrix-verdict-badge-${clauseId}`}
          data-matrix-verdict={matrixVerdict}
        >
          {verdictLabel(matrixVerdict)}
        </span>
      )}
      {counterpartyLabel && (
        <span
          className="text-[10px] text-muted-foreground"
          data-testid={`matrix-verdict-counterparty-${clauseId}`}
          data-counterparty-type={matrixCounterpartyType}
        >
          {counterpartyLabel}
        </span>
      )}
      {hasPopover && open && (
        <div
          role="dialog"
          aria-label="Matrix verdict lookup chain"
          data-testid={`matrix-verdict-popover-panel-${clauseId}`}
          className="mt-1 w-80 max-w-full rounded-md border bg-card p-3 text-xs shadow-sm"
        >
          <div className="mb-2 flex items-start justify-between gap-2">
            <div className="font-semibold uppercase tracking-wide text-muted-foreground">
              Lookup chain
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="text-muted-foreground hover:text-foreground"
              aria-label="Close matrix verdict popover"
              data-testid={`matrix-verdict-popover-close-${clauseId}`}
            >
              ×
            </button>
          </div>
          <ol
            className="space-y-1 font-mono"
            data-testid={`matrix-verdict-sources-${clauseId}`}
          >
            {(matrixSources ?? []).map((source, i) => (
              <li
                key={`${clauseId}-source-${i}`}
                className="text-foreground"
                data-testid={`matrix-verdict-source-${clauseId}-${i}`}
              >
                {source}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

export default MatrixVerdictCell;
