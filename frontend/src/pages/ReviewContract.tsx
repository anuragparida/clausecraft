import { useEffect, useState } from "react";
import { DeviationReviewPage } from "@/pages/DeviationReview";
import {
  useContractState,
  usePostDecisions,
  useSpot,
} from "@/lib/hooks";
import type {
  ContractStateResponse,
  Decision,
  IngestResponse,
  SpotResponse,
} from "@/lib/api";

// ReviewContract — the connected wrapper for the deviation
// review. Reached at ``/contracts/{contractId}/review``
// (the spec's "stable URL" for paused reviews). Owns the
// API plumbing: ingests the persisted checkpoint, re-runs
// the spotter if the clauses aren't cached, hydrates the
// page from any prior decisions, and submits the user's
// batch via the resume endpoint.
//
// Why a wrapper instead of putting API calls in DeviationReview
// ------------------------------------------------------------
// DeviationReview stays a pure "data in, events out" component
// (testable in isolation, no API mocks needed). The wrapper
// owns the network concerns. The Phase 2 tests on
// DeviationReview keep passing — they render the page with
// no onFlagDecision and a static ``data`` prop.
//
// State lifecycle
// ---------------
// 1. **Mount.** The page receives ``contractId`` from the
//    URL. When the parent (App.tsx) has clauses (the
//    "upload → review" hand-off path) it forwards them as
//    a prop. When the parent has nothing (the
//    "refresh-the-page" path), the wrapper fetches
//    ``GET /contracts/{id}/state`` to re-hydrate
//    clauses + prior spot flags + prior decisions. This is
//    the F3 fix from the Phase 3 review: without it, a
//    user who refreshed the URL mid-review saw a blank
//    page.
// 2. **Spot call.** If the state (or the parent prop)
//    provides clauses *and* no spot flags have been
//    cached server-side, the wrapper drives
//    ``POST /contracts/spot`` and stashes the result. If
//    the state already has flags, the wrapper uses them
//    as-is (the user might have refreshed in the middle
//    of a review; re-spotting would change the flag set
//    and silently lose decisions the user has already
//    made).
// 3. **User decides.** DeviationReview calls ``onFlagDecision``
//    for every change. The wrapper's handler writes the
//    decision to local state — that state is the source of
//    truth for the page UI (matches the "optimistic UI"
//    pattern from the spec's pause-and-resume test). Prior
//    decisions from the server are merged in on hydration.
// 4. **Generate redline.** DeviationReview calls
//    ``onSubmitDecisions(batch)``. The wrapper posts the
//    batch to ``/contracts/{id}/decisions`` and on success
//    navigates to the redline output page.
//
// Error / empty states
// --------------------
// The state endpoint always returns 200 — an unknown
// contract yields ``has_state=false`` with empty lists.
// The wrapper renders a friendly "this contract was not
// found" state in that case (a 404 here would force the
// user back to triage on a refresh, which is exactly the
// broken behaviour F3 is meant to fix).

export interface ReviewContractProps {
  /** The LangGraph thread id / contract id (from the URL). */
  contractId: string;
  /**
   * The clauses from the upstream ``POST /contracts/ingest``
   * call. The wrapper passes them straight to the spotter.
   * Optional: when omitted, the wrapper calls
   * ``GET /contracts/{contractId}/state`` to re-hydrate
   * clauses + flags + decisions. This is the F3 fix —
   * the previous build assumed the parent always handed
   * us the clauses, which it could not on a refresh.
   */
  clauses?: IngestResponse["clauses"];
  /** Filename for the spotter (and the audit log payload). */
  filename?: string;
  /** Pre-existing decisions (Build 3 will return these). */
  initialDecisions?: Decision[];
  /** Navigate to the redline output page. */
  onRedlineReady: () => void;
  /** Navigate to the audit replay page. */
  onViewAudit: () => void;
  /** Navigate back to home. */
  onBackToHome: () => void;
}

export function ReviewContractPage({
  contractId,
  clauses,
  filename,
  initialDecisions,
  onRedlineReady,
  onViewAudit,
  onBackToHome,
}: ReviewContractProps) {
  const [spot, setSpot] = useState<SpotResponse | null>(null);
  const [spotError, setSpotError] = useState<string | null>(null);
  const [decisions, setDecisions] = useState<Decision[]>(
    initialDecisions ?? [],
  );
  const [hydratedFromServer, setHydratedFromServer] = useState(false);
  const [hasIngested, setHasIngested] = useState<boolean>(
    Boolean(clauses && clauses.length > 0),
  );

  const spotMutation = useSpot();
  const submitMutation = usePostDecisions(contractId);
  const stateQuery = useContractState(contractId);

  // --- F3 hydration: fetch state on mount when the parent
  //     hands us no clauses. Runs once per mount.
  useEffect(() => {
    if (hydratedFromServer) return;
    if (clauses && clauses.length > 0) {
      // Parent gave us clauses; we don't need a server fetch.
      setHydratedFromServer(true);
      return;
    }
    if (!stateQuery.isFetched) {
      // Wait for the query to settle. ``isFetched`` flips
      // true on both success and error, so a 5xx will land
      // us in the error branch below.
      return;
    }
    const snap: ContractStateResponse | undefined = stateQuery.data;
    if (!snap || !snap.has_state || !snap.has_ingest) {
      // Nothing to hydrate from. The render path below
      // shows the "contract not found" empty state.
      setHydratedFromServer(true);
      return;
    }
    // Use the server-cached flags directly — re-running
    // the spotter would change the flag set and silently
    // drop the user's prior decisions. If the contract was
    // ingested but not yet spotted, ``snap.flags`` is empty
    // and we fall through to the spotter below.
    if (snap.flags && snap.flags.length > 0) {
      setSpot({
        filename: snap.filename,
        flag_count: snap.flags.length,
        flagged_count: snap.flags.filter((f) => f.score > 0).length,
        unverified_count: snap.flags.filter((f) => f.unverified).length,
        no_baseline_count: 0,
        matrix_version: "restored",
        embedding_provider: "restored",
        flags: snap.flags,
      });
    }
    // Hydrate prior decisions so the user sees their
    // earlier choices after a refresh.
    if (snap.decisions && snap.decisions.length > 0) {
      setDecisions(
        snap.decisions.map((d) => ({
          clause_id: d.clause_id,
          decision: mapCanonicalToAction(d),
          new_severity:
            typeof d.severity === "number" ? d.severity : undefined,
          old_severity:
            typeof d.old_severity === "number" ? d.old_severity : undefined,
          context: d.extra_context,
        })),
      );
    }
    setHasIngested(true);
    setHydratedFromServer(true);
  }, [hydratedFromServer, clauses, stateQuery.isFetched, stateQuery.data]);

  // --- Kick off the spot call when clauses are present and
  //     we have not already hydrated the spot response from
  //     server state. The mutation is one-shot.
  const [spotStarted, setSpotStarted] = useState(false);
  useEffect(() => {
    if (spotStarted) return;
    if (spot) return; // already hydrated
    if (!hasIngested) return;
    const activeClauses =
      clauses ?? (stateQuery.data?.has_ingest ? stateQuery.data?.clauses : null);
    if (!activeClauses || activeClauses.length === 0) return;
    setSpotStarted(true);
    spotMutation.mutate(
      { filename: filename ?? contractId, clauses: activeClauses },
      {
        onSuccess: (r) => {
          setSpot(r);
          setSpotError(null);
        },
        onError: (err) => {
          setSpotError(err.message);
        },
      },
    );
  }, [
    spotStarted,
    spot,
    hasIngested,
    clauses,
    filename,
    contractId,
    stateQuery.data,
    spotMutation,
  ]);

  const handleFlagDecision = (d: Decision) => {
    setDecisions((prev) => {
      // Upsert by clause_id. If a decision for this clause
      // already exists, replace it; otherwise append. (The
      // user's last action for a clause wins — a Reject
      // after an Approve replaces the Approve.)
      const filtered = prev.filter((p) => p.clause_id !== d.clause_id);
      return [...filtered, d];
    });
  };

  const handleSubmitDecisions = (batch: Decision[]) => {
    if (batch.length === 0) return;
    submitMutation.mutate(
      { decisions: batch },
      {
        onSuccess: () => {
          // Replace local decisions with the authoritative
          // server batch (the page's optimistic UI is now
          // confirmed). Then navigate to the redline
          // output.
          setDecisions(batch);
          onRedlineReady();
        },
        onError: (err) => {
          // Stay on the page; the user can retry. The
          // error is surfaced via the mutation's
          // ``error`` state below.
          setSpotError(err.message);
        },
      },
    );
  };

  // --- Render: friendly empty state when the state endpoint
  //     confirmed the contract does not exist on the
  //     server. (This is the F3 fix: refresh the URL with
  //     a typo'd contract id, and the user sees a clear
  //     message rather than a blank page.)
  if (hydratedFromServer && !hasIngested) {
    return (
      <div
        className="flex min-h-screen flex-col bg-background text-foreground"
        data-testid="review-contract-empty"
      >
        <main className="flex-1">
          <div className="mx-auto flex max-w-2xl flex-col gap-4 px-6 py-16">
            <header className="space-y-2">
              <h1 className="text-2xl font-semibold tracking-tight">
                Contract not found
              </h1>
              <p className="text-muted-foreground">
                No review state exists for contract id{" "}
                <code className="rounded bg-muted px-1 py-0.5 text-xs">
                  {contractId}
                </code>
                . The session may have been cleared, or the URL
                may have been mistyped.
              </p>
            </header>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={onBackToHome}
                className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium hover:bg-muted"
                data-testid="review-contract-back-home"
              >
                Back to home
              </button>
              <button
                type="button"
                onClick={onViewAudit}
                className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium hover:bg-muted"
                data-testid="review-contract-view-audit"
              >
                View audit log
              </button>
            </div>
          </div>
        </main>
      </div>
    );
  }

  // --- Render: error state when the state fetch failed
  //     (network error, 5xx, etc.). The user can retry or
  //     go back.
  if (hydratedFromServer && stateQuery.error && !hasIngested) {
    return (
      <div
        className="flex min-h-screen flex-col bg-background text-foreground"
        data-testid="review-contract-error"
      >
        <main className="flex-1">
          <div className="mx-auto flex max-w-2xl flex-col gap-4 px-6 py-16">
            <header className="space-y-2">
              <h1 className="text-2xl font-semibold tracking-tight">
                Could not load review
              </h1>
              <p className="text-muted-foreground">
                {stateQuery.error.message}
              </p>
            </header>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => stateQuery.refetch()}
                className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium hover:bg-muted"
              >
                Retry
              </button>
              <button
                type="button"
                onClick={onBackToHome}
                className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium hover:bg-muted"
              >
                Back to home
              </button>
            </div>
          </div>
        </main>
      </div>
    );
  }

  const data = spot
    ? {
        filename: spot.filename,
        flag_count: spot.flag_count,
        flagged_count: spot.flagged_count,
        unverified_count: spot.unverified_count,
        no_baseline_count: spot.no_baseline_count,
        matrix_version: spot.matrix_version,
        embedding_provider: spot.embedding_provider,
        flags: spot.flags.map((f) => ({
          clause_id: f.clause_id,
          score: f.score,
          rationale: f.rationale,
          citation: f.citation,
          unverified: f.unverified,
          baseline_type: f.baseline_type,
        })),
      }
    : null;

  return (
    <DeviationReviewPage
      data={data}
      loading={
        // Only show the "loading" skeleton until we know
        // whether the contract exists. Once hydration
        // completes, the spot call is the only pending
        // network request — and DeviationReview renders
        // its own "no flags" state when ``data`` is null.
        (!hydratedFromServer && stateQuery.isFetching) ||
        (hydratedFromServer && spotMutation.isPending && !spot)
      }
      error={spotError ?? submitMutation.error?.message ?? null}
      onBackToHome={onBackToHome}
      onBackToTriage={onViewAudit}
      initialDecisions={decisions}
      onFlagDecision={handleFlagDecision}
      onSubmitDecisions={handleSubmitDecisions}
      submitting={submitMutation.isPending}
      showGenerateRedline
    />
  );
}

// --- Helpers ------------------------------------------------------------


/**
 * Map a server-canonical decision (the shape stored in
 * ``phase3_pipeline.normalise_decision``) back to the
 * frontend's ``DecisionAction`` enum. Mirrors the inverse
 * of the action map in ``phase3_pipeline.normalise_decision``
 * — the two stay in lockstep so hydration is lossless.
 */
function mapCanonicalToAction(d: {
  action?: string;
}): Decision["decision"] {
  switch ((d.action ?? "").toLowerCase()) {
    case "accepted":
      return "approve";
    case "rejected":
      return "reject";
    case "edited":
      return "edit_severity";
    case "context_added":
      return "add_context";
    default:
      return "approve";
  }
}

export default ReviewContractPage;
