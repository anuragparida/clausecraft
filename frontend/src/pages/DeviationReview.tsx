import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { DisclaimerFooter } from "@/components/DisclaimerFooter";
import { SeverityBadge } from "@/components/SeverityBadge";
import { CitationPopover, type Citation } from "@/components/CitationPopover";
import { cn } from "@/lib/utils";

// DeviationReview — Phase 2 main work surface. Loads deviation
// flags (from a stub API or props; Phase 3 wires to backend) and
// renders a table with one row per flag. Each row carries:
//
//   - Clause reference + excerpt
//   - Severity badge (color-coded 0..3)
//   - Counterparty matrix verdict column (flat baseline verdict
//     for now — Phase 5 looks up the actual (clause_type ×
//     counterparty_type) verdict from the matrix loader)
//   - Citation popover (with "no citation" placeholder for
//     unverified flags)
//   - Per-row actions: Approve / Reject / Edit (local state only
//     in Phase 2; Phase 3 wires these to the audit log + LangGraph)
//
// "No baseline" handling: when a flag has ``unverified=True`` and
// ``rationale="no matching playbook clause"`` we render the row
// with a muted style (no severity badge, "no baseline" tag, the
// action buttons stay enabled so a human can still approve/reject
// the flag after reading it). The spec calls this out as
// "graceful 'no baseline' handling, not a crash".
//
// State machine (per row, in `states[clause_id]`):
//   - `action: "approved" | "rejected" | "edited" | null`
//     Persists across re-renders; rendered as the row's
//     `data-flag-action` attribute and as the action-button
//     variant (the selected button uses the *filled* variant).
//   - `editing: true` while the inline text input is open.
//     Transient: cleared on Save and on Cancel.
//   - `committedEdit: string | null` the rationale the user
//     committed by clicking Save. Rendered in the rationale cell
//     when present; falls back to the original flag rationale.
//
// Why split `editing` from `committedEdit`? Because the same
// `action === "edited"` should *both* keep the row's data-flag
// attribute as "edited" AND show the committed text in the
// rationale cell, but should NOT keep the input open after save.
// Treating "user is currently editing" as a separate flag keeps
// the action row and the rationale cell in sync without either
// fighting the other.

// --- API types ----------------------------------------------------------

/** Shape of a single flag in the `flags[]` array of `SpotResponse`. */
export interface DeviationFlag {
  clause_id: string;
  score: number;
  rationale: string;
  citation: Citation | null;
  unverified: boolean;
  baseline_type: string;
  // The API response may include the source URL on the
  // citation; the backend usually doesn't, but the page is
  // forward-compatible. (Phase 3 will populate this from the
  // playbook store lookup.)
  // source_url?: string;
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
}

// --- Constants ----------------------------------------------------------

/** Exact rationale string the spotter uses for "no matching playbook clause". */
const NO_BASELINE_RATIONALE = "no matching playbook clause";

const NO_BASELINE_LABEL = "no baseline";

/** Action a user can take on a flag. Persisted to local state in Phase 2. */
type FlagAction = "approved" | "rejected" | "edited" | null;

/**
 * Per-flag local state. The fields are independent:
 * - `action` persists until the user clicks a different action button.
 * - `editing` is transient: true only while the inline input is open.
 * - `committedEdit` is the value the user saved; rendered in the
 *   rationale cell when present.
 */
type FlagState = {
  action: FlagAction;
  editing: boolean;
  committedEdit: string | null;
};

function emptyFlagState(): FlagState {
  return { action: null, editing: false, committedEdit: null };
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

// --- Subcomponents ------------------------------------------------------

interface ActionRowProps {
  flag: DeviationFlag;
  state: FlagState;
  onApprove: () => void;
  onReject: () => void;
  onEdit: () => void;
  onSaveEdit: (newRationale: string) => void;
  onCancelEdit: () => void;
}

function ActionRow({
  flag,
  state,
  onApprove,
  onReject,
  onEdit,
  onSaveEdit,
  onCancelEdit,
}: ActionRowProps) {
  // The inline input's draft. Re-seeded via useEffect whenever
  // the parent flips `editing` back on (i.e. the user clicks Edit
  // again after a save). Without the effect, useState's
  // initialiser would only fire on the first mount of this row
  // instance and the second Edit click would show a stale draft.
  const initialDraft =
    state.committedEdit ?? flag.rationale;
  const [draft, setDraft] = useState(initialDraft);
  useEffect(() => {
    if (state.editing) {
      setDraft(state.committedEdit ?? flag.rationale);
    }
  }, [state.editing, state.committedEdit, flag.rationale]);

  if (state.editing) {
    return (
      <div
        className="flex flex-col gap-2"
        data-testid={`flag-action-row-edit-${flag.clause_id}`}
      >
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Edited rationale…"
          className="w-full rounded-md border bg-background px-2 py-1 text-xs"
          data-testid={`flag-edit-input-${flag.clause_id}`}
        />
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={() => onSaveEdit(draft)}
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
    </div>
  );
}

interface FlagTableProps {
  flags: DeviationFlag[];
  states: Record<string, FlagState>;
  onApprove: (clauseId: string) => void;
  onReject: (clauseId: string) => void;
  onEdit: (clauseId: string) => void;
  onSaveEdit: (clauseId: string, newRationale: string) => void;
  onCancelEdit: (clauseId: string) => void;
}

function FlagTable({
  flags,
  states,
  onApprove,
  onReject,
  onEdit,
  onSaveEdit,
  onCancelEdit,
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
                  <span
                    data-testid={`flag-matrix-verdict-${flag.clause_id}`}
                    data-matrix-verdict={scoreToVerdictLabel(flag.score)}
                  >
                    {scoreToVerdictLabel(flag.score)}
                  </span>
                  <div className="text-[10px] text-muted-foreground">
                    flat baseline (Phase 5 adds matrix)
                  </div>
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
                  {state.committedEdit ?? flag.rationale}
                </td>
                <td className="px-3 py-2">
                  <ActionRow
                    flag={flag}
                    state={state}
                    onApprove={() => onApprove(flag.clause_id)}
                    onReject={() => onReject(flag.clause_id)}
                    onEdit={() => onEdit(flag.clause_id)}
                    onSaveEdit={(newRationale) =>
                      onSaveEdit(flag.clause_id, newRationale)
                    }
                    onCancelEdit={() => onCancelEdit(flag.clause_id)}
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
// without the backend running. Phase 3 removes this in favour
// of a real fetch.

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
};

const SAMPLE_NO_BASELINE_FLAG: DeviationFlag = {
  clause_id: "c2",
  score: 0,
  rationale: NO_BASELINE_RATIONALE,
  citation: null,
  unverified: true,
  baseline_type: "",
};

export const SAMPLE_DEVIATION_REVIEW_DATA: DeviationReviewData = {
  filename: "sample-nda.pdf",
  flag_count: 2,
  flagged_count: 1,
  unverified_count: 1,
  no_baseline_count: 1,
  matrix_version: "phase2-flat",
  embedding_provider: "stub",
  flags: [SAMPLE_FLAG, SAMPLE_NO_BASELINE_FLAG],
};

// --- Page ---------------------------------------------------------------

export function DeviationReviewPage({
  data = null,
  loading = false,
  error = null,
  onBackToHome,
  onBackToTriage,
}: DeviationReviewProps) {
  // Per-flag local state. Phase 2 only — Phase 3 wires this to
  // a real audit log + LangGraph. The state is intentionally a
  // Record (not a Map) so React diffing works naturally and so
  // the parent can pass a pre-seeded state from props in tests.
  const [states, setStates] = useState<Record<string, FlagState>>({});

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

  const handleApprove = (clauseId: string) =>
    setStates((s) => {
      const current = s[clauseId] ?? emptyFlagState();
      return {
        ...s,
        [clauseId]: { ...current, action: "approved", editing: false },
      };
    });

  const handleReject = (clauseId: string) =>
    setStates((s) => {
      const current = s[clauseId] ?? emptyFlagState();
      return {
        ...s,
        [clauseId]: { ...current, action: "rejected", editing: false },
      };
    });

  const handleEdit = (clauseId: string) =>
    setStates((s) => {
      const current = s[clauseId] ?? emptyFlagState();
      return {
        ...s,
        [clauseId]: { ...current, action: "edited", editing: true },
      };
    });

  const handleSaveEdit = (clauseId: string, newRationale: string) =>
    setStates((s) => {
      const current = s[clauseId] ?? emptyFlagState();
      return {
        ...s,
        [clauseId]: {
          ...current,
          action: "edited",
          editing: false,
          committedEdit: newRationale.trim() || "(no rationale)",
        },
      };
    });

  const handleCancelEdit = (clauseId: string) =>
    setStates((s) => {
      const current = s[clauseId] ?? emptyFlagState();
      // Cancelling an Edit before any save means the action
      // reverts to null. Cancelling after a prior save keeps
      // the prior commit visible (the user can still see the
      // saved text and reopen Edit if they want).
      const next: FlagState = current.committedEdit
        ? { ...current, editing: false }
        : { action: null, editing: false, committedEdit: null };
      return { ...s, [clauseId]: next };
    });

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <main className="flex-1">
        <div className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-16">
          <header className="space-y-2">
            <h1 className="text-4xl font-bold tracking-tight">
              Deviation review
            </h1>
            <p className="text-muted-foreground">
              Phase 2 surface. Every flag the spotter emitted for the
              current contract, color-coded by severity, with
              citations and per-row actions. Buttons update local
              state only — persistence lands in Phase 3.
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
                />
              </CardContent>
            </Card>
          )}
        </div>
      </main>
      <DisclaimerFooter />
    </div>
  );
}

export default DeviationReviewPage;
