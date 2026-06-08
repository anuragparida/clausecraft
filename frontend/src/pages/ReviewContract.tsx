import { useState } from "react";
import { DeviationReviewPage } from "@/pages/DeviationReview";
import { usePostDecisions, useSpot } from "@/lib/hooks";
import type { Decision, IngestResponse, SpotResponse } from "@/lib/api";

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
//    URL. The wrapper holds the clauses + flags + prior
//    decisions in local state. On first render, all three
//    are empty (loading).
// 2. **Spot call.** The wrapper drives
//    ``POST /contracts/spot`` with the clauses it inherited
//    from the parent. (The parent is the upload flow, which
//    already called ``/contracts/ingest`` and stored the
//    clauses + contract id in localStorage or via a
//    router-state handoff. Build 6 will tighten this — for
//    Build 5 we accept either a ``clauses`` prop or a
//    re-fetch from the resume endpoint when Build 3 lands.)
// 3. **User decides.** DeviationReview calls ``onFlagDecision``
//    for every change. The wrapper's handler writes the
//    decision to local state — that state is the source of
//    truth for the page UI (matches the "optimistic UI"
//    pattern from the spec's pause-and-resume test).
// 4. **Generate redline.** DeviationReview calls
//    ``onSubmitDecisions(batch)``. The wrapper posts the
//    batch to ``/contracts/{id}/decisions`` and on success
//    navigates to the redline output page.

export interface ReviewContractProps {
  /** The LangGraph thread id / contract id (from the URL). */
  contractId: string;
  /**
   * The clauses from the upstream ``POST /contracts/ingest``
   * call. The wrapper passes them straight to the spotter.
   * Optional: when omitted, the wrapper calls the spotter
   * with an empty list (the spec's "refresh the page" path
   * may not have the clauses cached client-side — Build 3's
   * resume endpoint will need to return them in Build 6).
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

  const spotMutation = useSpot();
  const submitMutation = usePostDecisions(contractId);

  // Kick off the spot call on first mount when the parent
  // hands us clauses. The mutation is one-shot; we don't
  // refetch on every render. If the clauses prop is
  // missing, the page renders with no data — Build 6 will
  // add a re-fetch from the resume endpoint.
  const [spotStarted, setSpotStarted] = useState(false);
  if (!spotStarted && clauses && clauses.length > 0 && !spot) {
    setSpotStarted(true);
    spotMutation.mutate(
      { filename: filename ?? contractId, clauses },
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
  }

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
      loading={spotMutation.isPending && !spot}
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

export default ReviewContractPage;
