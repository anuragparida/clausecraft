import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { DisclaimerFooter } from "@/components/DisclaimerFooter";
import { SeverityBadge } from "@/components/SeverityBadge";
import { CitationPopover, type Citation } from "@/components/CitationPopover";
import { MatrixVerdictCell, type MatrixVerdict, type CounterpartyTypeForCell } from "@/components/MatrixVerdictCell";
import { cn } from "@/lib/utils";
import type { Decision } from "@/lib/api";

// DeviationReview — the main work surface. Renders one row per
// deviation flag with per-row actions and a footer-level
// "Generate redline" CTA.
//
// Phase 2 was local-state only. Phase 3 wires the buttons to a
// real backend (the LangGraph HITL pipeline) and to the
// append-only audit log. The page is **dual-mode**:
//
// - **Uncontrolled** (default). When ``onFlagDecision`` and
//   ``onSubmitDecisions`` are not provided, all decisions live
//   in local React state. The Phase 2 tests exercise this path
//   — the test suite never has to mock the API.
//
// - **Controlled** (Phase 3 in production). The connected page
//   (``pages/ReviewContract.tsx``) passes an ``onFlagDecision``
//   callback that writes a single audit event for each click,
//   plus an ``onSubmitDecisions`` callback that runs the resume
//   mutation. The local state is still maintained for the UI
//   (the spec says "pause-and-resume is testable" — the local
//   state is the optimistic UI, the backend is the source of
//   truth on refresh).
//
// Why the dual-mode shape
// -----------------------
// The Phase 2 visual layout is approved (Helena's Review 1
// passed). Build 5's hard rule is "wire the existing buttons,
// don't replace them". Keeping the page headless (props in,
// events out) means the visual layout file is testable in
// isolation and the API plumbing lives in a connected wrapper.

// --- API types ---------------------------------------------------------

/** Shape of a single flag in the `flags[]` array of `SpotResponse`. */
export interface DeviationFlag {
  clause_id: string;
  score: number;
  rationale: string;
  citation: Citation | null;
  unverified: boolean;
  baseline_type: string;
  // Phase 5: the matrix verdict + lookup chain that
  // produced the spotter's audit column. Optional
  // because the Phase 2/3/4 backends never set them
  // (the spec locks the 4-state column forward-only).
  matrix_verdict?: MatrixVerdict;
  matrix_sources?: string[];
  matrix_counterparty_type?: CounterpartyTypeForCell;
}

/** Subset of `SpotResponse` this page consumes. */
export interface DeviationReviewData {
  filename: string;
  flag_count: number;
  flagged_count: number;
  unverified_count: number;
  no_baseline_count: number;
  matrix_version: string;
  embedding_provider: string;
  flags: DeviationFlag[];
}

export interface DeviationReviewProps {
  data?: DeviationReviewData | null;
  /** Loading state when the parent is fetching from the API. */
  loading?: boolean;
  /** Error state from the parent's fetch. */
  error?: string | null;
  /** Back-to-home navigation. Required. */
  onBackToHome: () => void;
  /** Back-to-triage navigation. Optional but recommended. */
  onBackToTriage?: () => void;
  /**
   * Pre-existing decisions restored from a backend fetch
   * (the "refresh the page" resume path). When present, the
   * page hydrates its local state from this array instead of
   * starting empty.
   */
  initialDecisions?: Decision[];
  /**
   * Fired on every flag-state change (approve / reject / save
   * edit / cancel edit / add context). The connected page
   * turns this into a per-flag audit event.
   */
  onFlagDecision?: (decision: Decision) => void;
  /**
   * Fired when the user clicks "Generate redline" (every
   * flag has a decision). The connected page POSTs the
   * decision batch to ``/contracts/{id}/decisions``.
   */
  onSubmitDecisions?: (decisions: Decision[]) => void;
  /**
   * Whether the "Generate redline" submission is in flight.
   * Disables the button and shows a spinner label.
   */
  submitting?: boolean;
  /**
   * When true, the "Generate redline" button is rendered.
   * The standalone home-view path doesn't show it (the
   * connected review page does).
   */
  showGenerateRedline?: boolean;
}

// --- Constants ---------------------------------------------------------

/** Exact rationale string the spotter uses for "no matching playbook clause". */
const NO_BASELINE_RATIONALE = "no matching playbook clause";

const NO_BASELINE_LABEL = "no baseline";

/** Action a user can take on a flag. Persisted to local state. */
type FlagAction = "approved" | "rejected" | "edited" | null;

/**
 * Per-flag local state. The fields are independent:
 * - `action` persists until the user clicks a different action button.
 * - `editing` is transient: true only while the inline input is open.
 * - `committedSeverity` is the value the user saved; the row's
 *   severity badge re-renders with this value when present. The
 *   backend reads `new_severity` off the decision, so this is
 *   what the user actually "edited" (per spec line 231: Edit is
 *   the severity override).
 * - `extraContext` is the free-form context from "Add context".
 * - `addingContext` is transient: true only while the add-context
 *   textarea is open.
 */
type FlagState = {
  action: FlagAction;
  editing: boolean;
  committedSeverity: number | null;
  /** Free-form context the user attached via "Add context". */
  extraContext: string | null;
  /** Transient: true only while the add-context textarea is open. */
  addingContext: boolean;
};

function emptyFlagState(): FlagState {
  return {
    action: null,
    editing: false,
    committedSeverity: null,
    extraContext: null,
    addingContext: false,
  };
}

function isNoBaselineFlag(flag: DeviationFlag): boolean {
  return (
    flag.unverified &&
    flag.rationale.trim().toLowerCase() === NO_BASELINE_RATIONALE
  );
}

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

/**
 * Map the page's local ``FlagState`` to the wire-shape
 * :class:`Decision` the backend expects.
 *
 * Returns ``null`` for the "no decision yet" case (the row
 * hasn't been touched) so the caller can filter those out
 * before building the decisions batch.
 */
function flagStateToDecision(
  clauseId: string,
  state: FlagState,
  originalRationale: string,
  originalScore: number,
): Decision | null {
  // The wire-shape maps one Decision per clause (Build 3's
  // resume endpoint takes a flat ``decisions[]`` array).
  // When the user has both an action AND a saved context,
  // the more-recent one wins: the user can re-click
  // "Add context" after an Approve to attach a note, and
  // that note is the latest intent. (Reviewing a clause,
  // the reviewer cares about "what's the most recent thing
  // the user said about this row" — and a typed context is
  // more recent than a button click.)
  if (state.extraContext) {
    return {
      clause_id: clauseId,
      decision: "add_context",
      context: state.extraContext,
    };
  }
  if (state.action === "approved") {
    return { clause_id: clauseId, decision: "approve" };
  }
  if (state.action === "rejected") {
    return { clause_id: clauseId, decision: "reject" };
  }
  if (state.action === "edited") {
    return {
      clause_id: clauseId,
      decision: "edit_severity",
      // The committed severity is the value the user typed
      // in the inline number input. The backend's audit
      // event for ``severity_edited`` includes both
      // ``old_severity`` and ``new_severity``; the old
      // value is the spotter's original score.
      new_severity:
        state.committedSeverity !== null ? state.committedSeverity : originalScore,
      old_severity: originalScore,
    };
  }
  // No decision yet. (This branch is hit for a row that the
  // user has not interacted with, or for an "edited" row
  // whose committedSeverity was cleared by a later "cancel".)
  void originalRationale;
  return null;
}

// --- Subcomponents ------------------------------------------------------

interface ActionRowProps {
  flag: DeviationFlag;
  state: FlagState;
  onApprove: () => void;
  onReject: () => void;
  onEdit: () => void;
  onSaveEdit: (newSeverity: number) => void;
  onCancelEdit: () => void;
  onAddContext: () => void;
  onSaveContext: (context: string) => void;
  onCancelContext: () => void;
}

function ActionRow({
  flag,
  state,
  onApprove,
  onReject,
  onEdit,
  onSaveEdit,
  onCancelEdit,
  onAddContext,
  onSaveContext,
  onCancelContext,
}: ActionRowProps) {
  // The inline input's draft. The spec (line 231) is
  // explicit: Edit is the severity override. The input is
  // ``<input type="number" min="0" max="3">`` so the
  // browser enforces the spotter's 4-level scale. The
  // draft is seeded from the committed severity (when
  // the user re-opens an already-saved edit) or the
  // spotter's original score (the natural starting
  // point for a fresh edit).
  const initialSeverityDraft =
    state.committedSeverity ?? flag.score;
  const [severityDraft, setSeverityDraft] = useState(
    String(initialSeverityDraft),
  );
  useEffect(() => {
    if (state.editing) {
      setSeverityDraft(
        String(state.committedSeverity ?? flag.score),
      );
    }
  }, [state.editing, state.committedSeverity, flag.score]);

  // Same dance for the Add-context draft. The draft
  // re-seeds whenever the parent flips ``addingContext``
  // back on, so a "click Add context again to re-edit"
  // path shows the previous text, not a stale empty
  // string.
  const [contextDraft, setContextDraft] = useState(state.extraContext ?? "");
  useEffect(() => {
    if (state.addingContext) {
      setContextDraft(state.extraContext ?? "");
    }
  }, [state.addingContext, state.extraContext]);

  // If the row's editing state flips open, show the edit UI.
  if (state.editing) {
    return (
      <div
        className="flex flex-col gap-2"
        data-testid={`flag-action-row-edit-${flag.clause_id}`}
      >
        <label
          className="flex items-center gap-2 text-xs"
          data-testid={`flag-edit-label-${flag.clause_id}`}
        >
          <span>Severity (0–3):</span>
          <input
            type="number"
            min={0}
            max={3}
            step={1}
            value={severityDraft}
            onChange={(e) => setSeverityDraft(e.target.value)}
            className="w-16 rounded-md border bg-background px-2 py-1 text-xs"
            data-testid={`flag-edit-input-${flag.clause_id}`}
          />
          <span className="text-muted-foreground">
            (was {flag.score}: {scoreToVerdictLabel(flag.score)})
          </span>
        </label>
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={() => {
              // Clamp to [0, 3] so a stray keystroke
              // (e.g. "5") doesn't end up in the
              // decision payload. Empty input is a no-op
              // — the user can cancel without saving.
              const n = Number(severityDraft);
              if (!Number.isFinite(n)) return;
              const clamped = Math.max(0, Math.min(3, Math.round(n)));
              onSaveEdit(clamped);
            }}
            data-testid={`flag-save-edit-${flag.clause_id}`}
          >
            Save
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={onCancelEdit}
            data-testid={`flag-cancel-edit-${flag.clause_id}`}
          >
            Cancel
          </Button>
        </div>
      </div>
    );
  }

  // The "add context" sub-UI. Triggered by a transient
  // ``state.addingContext`` flag set by the parent when
  // the user clicks the "Add context" button. Render the
  // textarea with the previously-saved value (if any) as
  // the draft.
  if (state.addingContext) {
    return (
      <div
        className="flex flex-col gap-2"
        data-testid={`flag-action-row-context-${flag.clause_id}`}
      >
        <textarea
          value={contextDraft}
          onChange={(e) => setContextDraft(e.target.value)}
          placeholder="Free-form context…"
          className="w-full rounded-md border bg-background px-2 py-1 text-xs"
          rows={3}
          data-testid={`flag-context-input-${flag.clause_id}`}
        />
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={() => onSaveContext(contextDraft)}
            data-testid={`flag-save-context-${flag.clause_id}`}
          >
            Save
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={onCancelContext}
            data-testid={`flag-cancel-context-${flag.clause_id}`}
          >
            Cancel
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="flex flex-wrap gap-2"
      data-testid={`flag-action-row-${flag.clause_id}`}
      data-flag-action={state.action ?? "none"}
    >
      <Button
        size="sm"
        variant={state.action === "approved" ? "default" : "outline"}
        onClick={onApprove}
        data-testid={`flag-approve-${flag.clause_id}`}
      >
        Approve
      </Button>
      <Button
        size="sm"
        variant={state.action === "rejected" ? "destructive" : "outline"}
        onClick={onReject}
        data-testid={`flag-reject-${flag.clause_id}`}
      >
        Reject
      </Button>
      <Button
        size="sm"
        variant={state.action === "edited" ? "secondary" : "outline"}
        onClick={onEdit}
        data-testid={`flag-edit-${flag.clause_id}`}
      >
        Edit
      </Button>
      <Button
        size="sm"
        variant={state.extraContext ? "secondary" : "outline"}
        onClick={onAddContext}
        data-testid={`flag-add-context-${flag.clause_id}`}
      >
        Add context
      </Button>
      {state.extraContext && (
        <span
          className="text-xs text-muted-foreground"
          data-testid={`flag-context-saved-${flag.clause_id}`}
        >
          context saved
        </span>
      )}
    </div>
  );
}

interface FlagTableProps {
  flags: DeviationFlag[];
  states: Record<string, FlagState>;
  onApprove: (clauseId: string) => void;
  onReject: (clauseId: string) => void;
  onEdit: (clauseId: string) => void;
  onSaveEdit: (clauseId: string, newSeverity: number) => void;
  onCancelEdit: (clauseId: string) => void;
  onAddContext: (clauseId: string) => void;
  onSaveContext: (clauseId: string, context: string) => void;
  onCancelContext: (clauseId: string) => void;
}

function FlagTable({
  flags,
  states,
  onApprove,
  onReject,
  onEdit,
  onSaveEdit,
  onCancelEdit,
  onAddContext,
  onSaveContext,
  onCancelContext,
}: FlagTableProps) {
  if (flags.length === 0) {
    return (
      <p
        className="text-sm text-muted-foreground"
        data-testid="deviation-review-empty"
      >
        No deviation flags. The spotter ran but found nothing to
        flag — every clause either matched its baseline or had no
        matching baseline to compare against.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto rounded-md border">
      <table
        className="w-full text-sm"
        data-testid="deviation-review-table"
      >
        <thead className="bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-3 py-2 font-medium">Clause</th>
            <th className="px-3 py-2 font-medium">Severity</th>
            <th className="px-3 py-2 font-medium">Matrix verdict</th>
            <th className="px-3 py-2 font-medium">Citation</th>
            <th className="px-3 py-2 font-medium">Rationale</th>
            <th className="px-3 py-2 font-medium">Action</th>
          </tr>
        </thead>
        <tbody>
          {flags.map((flag) => {
            const isNoBaseline = isNoBaselineFlag(flag);
            const state = states[flag.clause_id] ?? emptyFlagState();
            return (
              <tr
                key={flag.clause_id}
                data-testid={`deviation-row-${flag.clause_id}`}
                data-no-baseline={isNoBaseline ? "true" : "false"}
                data-flag-action={state.action ?? "none"}
                className={cn(
                  "border-t align-top",
                  isNoBaseline && "bg-muted/40 text-muted-foreground"
                )}
              >
                <td className="px-3 py-2 font-mono text-xs">
                  <div>{flag.clause_id}</div>
                  {flag.baseline_type && (
                    <div className="text-[10px] text-muted-foreground">
                      {flag.baseline_type}
                    </div>
                  )}
                </td>
                <td className="px-3 py-2">
                  {isNoBaseline ? (
                    <Badge
                      variant="type-unknown"
                      data-testid={`flag-no-baseline-badge-${flag.clause_id}`}
                    >
                      {NO_BASELINE_LABEL}
                    </Badge>
                  ) : (
                    <SeverityBadge score={flag.score} />
                  )}
                </td>
                <td className="px-3 py-2 text-xs">
                  <MatrixVerdictCell
                    clauseId={flag.clause_id}
                    matrixVerdict={flag.matrix_verdict}
                    matrixSources={flag.matrix_sources}
                    matrixCounterpartyType={flag.matrix_counterparty_type}
                    score={flag.score}
                  />
                </td>
                <td className="px-3 py-2">
                  <CitationPopover
                    citation={flag.citation}
                    unverified={flag.unverified}
                  />
                </td>
                <td
                  className="px-3 py-2 text-xs"
                  data-testid={`flag-rationale-${flag.clause_id}`}
                >
                  {flag.rationale}
                  {state.committedSeverity !== null && state.committedSeverity !== flag.score && (
                    <div
                      className="mt-1 border-l-2 border-muted pl-2 text-[11px] text-muted-foreground"
                      data-testid={`flag-severity-cell-${flag.clause_id}`}
                    >
                      <span className="font-semibold">Severity: </span>
                      {flag.score} → {state.committedSeverity} (
                      {scoreToVerdictLabel(state.committedSeverity)})
                    </div>
                  )}
                  {state.extraContext && (
                    <div
                      className="mt-1 border-l-2 border-muted pl-2 text-[11px] text-muted-foreground"
                      data-testid={`flag-context-cell-${flag.clause_id}`}
                    >
                      <span className="font-semibold">Context: </span>
                      {state.extraContext}
                    </div>
                  )}
                </td>
                <td className="px-3 py-2">
                  <ActionRow
                    flag={flag}
                    state={state}
                    onApprove={() => onApprove(flag.clause_id)}
                    onReject={() => onReject(flag.clause_id)}
                    onEdit={() => onEdit(flag.clause_id)}
                    onSaveEdit={(newSeverity) =>
                      onSaveEdit(flag.clause_id, newSeverity)
                    }
                    onCancelEdit={() => onCancelEdit(flag.clause_id)}
                    onAddContext={() => onAddContext(flag.clause_id)}
                    onSaveContext={(context) =>
                      onSaveContext(flag.clause_id, context)
                    }
                    onCancelContext={() => onCancelContext(flag.clause_id)}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// --- Sample data --------------------------------------------------------
//
// Used when the parent passes no `data` prop. Renders a small
// fixture with 0/1/N flags so the page is reachable end-to-end
// without the backend running. Phase 3 keeps this as the
// standalone-home-view's demo content.

const SAMPLE_FLAG: DeviationFlag = {
  clause_id: "c1",
  score: 2,
  rationale:
    "Term is '7 years' against a 3-year baseline — material deviation.",
  citation: {
    playbook_clause_id: "nda-en::term::001",
    contract_text_excerpt:
      "The obligations of confidentiality shall continue for a period of seven (7) years from the Effective Date.",
    source_url: "https://example.com/nda-baselines/term",
  },
  unverified: false,
  baseline_type: "term",
  // Phase 5 sample: the matrix verdict for a term-clause
  // against an enterprise counterparty type. The lookup
  // chain shows the cell that produced the verdict.
  matrix_verdict: "material",
  matrix_sources: [
    "term (counterparty, enterprise)",
    "term (counterparty, flat)",
  ],
  matrix_counterparty_type: "enterprise",
};

const SAMPLE_NO_BASELINE_FLAG: DeviationFlag = {
  clause_id: "c2",
  score: 0,
  rationale: NO_BASELINE_RATIONALE,
  citation: null,
  unverified: true,
  baseline_type: "",
};

/** A second matrix-aware row demonstrating the
 *  unacceptable verdict on a healthcare counterparty
 *  type — the per-type escalation card's v2 rule
 *  promotes score-2 to "unacceptable" for healthcare
 *  and public_sector (see card t_7c0ca277). The
 *  popover surfaces the lookup chain. */
const SAMPLE_MATRIX_ESCALATION_FLAG: DeviationFlag = {
  clause_id: "c3",
  score: 2,
  rationale:
    "Audit rights clause: 30-day notice vs. baseline 14-day — material deviation escalated to unacceptable for healthcare (HIPAA / sector-specific data protection).",
  citation: {
    playbook_clause_id: "dpa-en::dpa_audit_rights::001",
    contract_text_excerpt:
      "The Processor shall make available to the Controller, upon 30 days' prior written notice, all information necessary to demonstrate compliance with this DPA.",
    source_url: "https://example.com/dpa-baselines/audit-rights",
  },
  unverified: false,
  baseline_type: "dpa_audit_rights",
  matrix_verdict: "unacceptable",
  matrix_sources: [
    "dpa_audit_rights (counterparty, healthcare)",
    "dpa_audit_rights (counterparty, flat)",
  ],
  matrix_counterparty_type: "healthcare",
};

export const SAMPLE_DEVIATION_REVIEW_DATA: DeviationReviewData = {
  filename: "sample-nda.pdf",
  flag_count: 3,
  flagged_count: 2,
  unverified_count: 1,
  no_baseline_count: 1,
  matrix_version: "phase5-4axis",
  embedding_provider: "stub",
  flags: [
    SAMPLE_FLAG,
    SAMPLE_NO_BASELINE_FLAG,
    SAMPLE_MATRIX_ESCALATION_FLAG,
  ],
};

// --- Page ---------------------------------------------------------------

export function DeviationReviewPage({
  data = null,
  loading = false,
  error = null,
  onBackToHome,
  onBackToTriage,
  initialDecisions,
  onFlagDecision,
  onSubmitDecisions,
  submitting = false,
  showGenerateRedline = false,
}: DeviationReviewProps) {
  // Per-flag local state. The page is a controlled/uncontrolled
  // hybrid: the state is always local, but on every state
  // change we also fire ``onFlagDecision`` so the connected
  // page can persist. The Phase 2 tests use the page in
  // uncontrolled mode (no onFlagDecision), which is why the
  // existing assertions still hold.
  const [states, setStates] = useState<Record<string, FlagState>>({});

  // Hydrate from ``initialDecisions`` on first mount. This is
  // the "refresh the page" resume path: the connected page
  // fetches prior decisions from the backend, then passes
  // them in; the page converts them back to local state so
  // the UI shows "what the user already decided".
  useEffect(() => {
    if (!initialDecisions || initialDecisions.length === 0) return;
    setStates((prev) => {
      const next: Record<string, FlagState> = { ...prev };
      for (const d of initialDecisions) {
        const existing = next[d.clause_id] ?? emptyFlagState();
        if (d.decision === "approve") {
          next[d.clause_id] = { ...existing, action: "approved", editing: false };
        } else if (d.decision === "reject") {
          next[d.clause_id] = { ...existing, action: "rejected", editing: false };
        } else if (d.decision === "edit_severity") {
          // The backend's edit_severity decision carries
          // the new severity. We restore both the
          // action and the committed severity so the row
          // re-renders the "old → new" badge.
          next[d.clause_id] = {
            ...existing,
            action: "edited",
            editing: false,
            committedSeverity:
              typeof d.new_severity === "number" ? d.new_severity : null,
          };
        } else if (d.decision === "add_context") {
          next[d.clause_id] = {
            ...existing,
            extraContext: d.context ?? existing.extraContext,
          };
        }
      }
      return next;
    });
    // We deliberately do NOT re-run on every change of
    // initialDecisions — the page should only hydrate
    // once. The empty dep-array would be a lint error in
    // strict mode; the `initialDecisions` dep is correct
    // because the connected page passes a stable array
    // (memoised) for the lifetime of the contract.
  }, [initialDecisions]);

  const flags = data?.flags ?? [];
  const sortedFlags = useMemo(() => {
    // Sort: non-baseline flags last, then by score desc, then by
    // clause_id asc. Stable for tests.
    return [...flags].sort((a, b) => {
      const aNo = isNoBaselineFlag(a) ? 1 : 0;
      const bNo = isNoBaselineFlag(b) ? 1 : 0;
      if (aNo !== bNo) return aNo - bNo;
      if (a.score !== b.score) return b.score - a.score;
      return a.clause_id.localeCompare(b.clause_id);
    });
  }, [flags]);

  // Helper that updates state AND fires the onFlagDecision
  // callback (when present). This is the single chokepoint
  // for every UI mutation so the connected page can persist
  // without each handler re-implementing the dispatch.
  const mutate = (
    clauseId: string,
    next: FlagState | ((s: FlagState) => FlagState),
    emit: (d: Decision) => void,
  ) => {
    setStates((s) => {
      const current = s[clauseId] ?? emptyFlagState();
      const updated = typeof next === "function" ? next(current) : next;
      const original = flags.find((f) => f.clause_id === clauseId);
      const decision = flagStateToDecision(
        clauseId,
        updated,
        original?.rationale ?? "",
        original?.score ?? 0,
      );
      if (decision && onFlagDecision) {
        // Only emit a decision when the state actually
        // crossed into a "decided" configuration. The
        // helper above always returns a Decision for
        // approved/rejected/edited/extraContext, so this
        // gate is a no-op for the happy path. (If a
        // future refactor adds a "decision: null" return
        // for transient states — e.g. opening the edit
        // input — this gate suppresses the spurious
        // emit.)
        emit(decision);
      }
      return { ...s, [clauseId]: updated };
    });
  };

  const handleApprove = (clauseId: string) =>
    mutate(
      clauseId,
      (s) => ({ ...s, action: "approved", editing: false }),
      onFlagDecision ?? noop,
    );

  const handleReject = (clauseId: string) =>
    mutate(
      clauseId,
      (s) => ({ ...s, action: "rejected", editing: false }),
      onFlagDecision ?? noop,
    );

  const handleEdit = (clauseId: string) =>
    // Open the edit input. This is a transient UI state;
    // we do NOT emit a Decision here (the user's intent
    // is "I want to type", not "I want to commit a
    // change"). The emit happens on Save.
    setStates((s) => {
      const current = s[clauseId] ?? emptyFlagState();
      return {
        ...s,
        [clauseId]: { ...current, action: "edited", editing: true },
      };
    });

  const handleSaveEdit = (clauseId: string, newSeverity: number) =>
    mutate(
      clauseId,
      (s) => ({
        ...s,
        action: "edited",
        editing: false,
        committedSeverity: newSeverity,
      }),
      onFlagDecision ?? noop,
    );

  const handleCancelEdit = (clauseId: string) =>
    setStates((s) => {
      const current = s[clauseId] ?? emptyFlagState();
      // Cancelling an Edit before any save means the action
      // reverts to null. Cancelling after a prior save keeps
      // the prior commit visible (the user can still see the
      // saved severity and reopen Edit if they want).
      const next: FlagState = current.committedSeverity !== null
        ? { ...current, editing: false }
        : {
            action: null,
            editing: false,
            committedSeverity: null,
            extraContext: current.extraContext,
            addingContext: current.addingContext,
          };
      return { ...s, [clauseId]: next };
    });

  const handleAddContext = (clauseId: string) =>
    // Open the add-context input. We don't emit a
    // Decision until the user clicks Save.
    setStates((s) => {
      const current = s[clauseId] ?? emptyFlagState();
      return {
        ...s,
        [clauseId]: { ...current, addingContext: true },
      };
    });

  const handleSaveContext = (clauseId: string, context: string) =>
    mutate(
      clauseId,
      (s) => ({
        ...s,
        extraContext: context.trim() || null,
        addingContext: false,
      }),
      onFlagDecision ?? noop,
    );

  const handleCancelContext = (clauseId: string) =>
    setStates((s) => {
      const current = s[clauseId] ?? emptyFlagState();
      // Same dance as Edit-cancel: a previously-saved
      // context stays; the transient input closes.
      return {
        ...s,
        [clauseId]: { ...current, addingContext: false },
      };
    });

  // --- Generate redline gating ---------------------------------------
  //
  // The button is enabled when every flag has a decision (an
  // explicit "approved" / "rejected" / "edited" / "context
  // added" — anything that maps to a Decision on the wire).
  // We intentionally do NOT require every flag to be
  // approved: a user may legitimately reject 4 of 5 flags
  // and only want a redline for the 1 they approved. The
  // graph handles "no redlines needed" gracefully.

  const allDecided = useMemo(() => {
    if (!data || data.flags.length === 0) return false;
    return data.flags.every((flag) => {
      const state = states[flag.clause_id];
      if (!state) return false;
      // "decided" means: any of the four actions is set, OR
      // a context was added, OR a severity was edited (the
      // committedSeverity is non-null even if the user
      // happens to have typed the same value as the
      // spotter's — the edit intent still counts).
      return (
        state.action === "approved" ||
        state.action === "rejected" ||
        state.action === "edited" ||
        state.committedSeverity !== null ||
        (state.extraContext !== null && state.extraContext !== undefined)
      );
    });
  }, [data, states]);

  const handleGenerateRedline = () => {
    if (!onSubmitDecisions) return;
    if (!data) return;
    const batch: Decision[] = [];
    for (const flag of data.flags) {
      const state = states[flag.clause_id];
      if (!state) continue;
      const d = flagStateToDecision(
        flag.clause_id,
        state,
        flag.rationale,
        flag.score,
      );
      if (d) batch.push(d);
    }
    onSubmitDecisions(batch);
  };

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <main className="flex-1">
        <div className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-16">
          <header className="space-y-2">
            <h1 className="text-4xl font-bold tracking-tight">
              Deviation review
            </h1>
            <p className="text-muted-foreground">
              Every flag the spotter emitted for the current
              contract, color-coded by severity, with citations
              and per-row actions. Approve / Reject / Edit /
              Add-context each write a row to the append-only
              audit log; "Generate redline" runs the redline
              drafter on the accepted flags.
            </p>
          </header>

          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={onBackToHome}
              data-testid="deviation-back-home"
            >
              Home
            </Button>
            {onBackToTriage && (
              <Button
                variant="outline"
                onClick={onBackToTriage}
                data-testid="deviation-back-triage"
              >
                Back to Triage
              </Button>
            )}
          </div>

          {loading && (
            <p className="text-sm text-muted-foreground">Loading flags…</p>
          )}
          {error && (
            <div
              className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive"
              role="alert"
              data-testid="deviation-review-error"
            >
              {error}
            </div>
          )}

          {data && (
            <Card>
              <CardHeader>
                <CardTitle>
                  <span className="font-mono">{data.filename}</span>
                </CardTitle>
                <CardDescription>
                  {data.flag_count} flags · {data.flagged_count} non-zero ·{" "}
                  {data.unverified_count} unverified · {data.no_baseline_count}{" "}
                  no-baseline · matrix {data.matrix_version} · embeddings{" "}
                  {data.embedding_provider}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <FlagTable
                  flags={sortedFlags}
                  states={states}
                  onApprove={handleApprove}
                  onReject={handleReject}
                  onEdit={handleEdit}
                  onSaveEdit={handleSaveEdit}
                  onCancelEdit={handleCancelEdit}
                  onAddContext={handleAddContext}
                  onSaveContext={handleSaveContext}
                  onCancelContext={handleCancelContext}
                />
                {showGenerateRedline && (
                  <div
                    className="flex items-center justify-between border-t pt-4"
                    data-testid="generate-redline-bar"
                  >
                    <p
                      className="text-xs text-muted-foreground"
                      data-testid="generate-redline-status"
                    >
                      {allDecided
                        ? "Every flag has a decision. You can generate the redline now."
                        : "Decide every flag (approve / reject / edit / add context) before generating the redline."}
                    </p>
                    <Button
                      onClick={handleGenerateRedline}
                      disabled={!allDecided || submitting}
                      data-testid="generate-redline-button"
                    >
                      {submitting ? "Generating…" : "Generate redline"}
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </main>
      <DisclaimerFooter />
    </div>
  );
}

function noop(): void {
  /* no-op fallback for the onFlagDecision prop */
}

export default DeviationReviewPage;
