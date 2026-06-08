// react-query hooks wrapping the Phase 3 API client.
//
// Conventions
// -----------
// - Each hook returns a react-query useQuery / useMutation
//   result. Components consume ``data`` / ``error`` / ``isLoading``.
// - The query keys are stable arrays so a caller can
//   ``queryClient.invalidateQueries({queryKey: ["contract", id]})``.
// - Mutations invalidate the relevant query keys on success —
//   e.g. posting a decision invalidates the audit log query so
//   the next fetch sees the new event row.
//
// Why a separate hooks file
// -------------------------
// Pages can stay focused on layout. The query keys + cache
// invalidation live in one place; reviewers checking "does the
// audit-replay view refresh after a decision?" can read this
// file in one screenful.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  type Decision,
  type DecisionsBody,
  type IngestResponse,
  type SpotResponse,
  getAuditLogJson,
  getAuditLogPdf,
  getRedlineDocx,
  postDecisions,
  postIngest,
  postSpot,
  spotResponseToReviewData,
} from "@/lib/api";

// --- Query keys --------------------------------------------------------
//
// Single source of truth for the cache namespace. The pattern
// is ``["contract", contractId, "resource", ...]`` so a
// "refresh this contract" invalidation can target the whole
// subtree.

export const queryKeys = {
  contract: (id: string) => ["contract", id] as const,
  spot: (id: string) => ["contract", id, "spot"] as const,
  auditLog: (id: string) => ["contract", id, "audit-log"] as const,
};

// --- Hooks -------------------------------------------------------------

/** POST /contracts/ingest. Upload a file, get clauses + a contract id. */
export function useIngest() {
  return useMutation<IngestResponse, Error, { file: File; language?: "en" | "de" }>({
    mutationFn: ({ file, language }) => postIngest(file, language),
  });
}

/**
 * POST /contracts/spot. Drives the deviation spotter on an
 * already-ingested clause list. The hook returns the
 * :class:`SpotResponse` directly; the caller (DeviationReview)
 * is responsible for the ``spotResponseToReviewData`` adapter
 * when it needs the DeviationReviewData shape.
 */
export function useSpot() {
  return useMutation<
    SpotResponse,
    Error,
    { filename: string; clauses: IngestResponse["clauses"] }
  >({
    mutationFn: (payload) => postSpot(payload),
  });
}

/**
 * Resume the graph with a batch of per-flag decisions. On
 * success, the audit log query is invalidated so the next
 * fetch picks up the new events.
 */
export function usePostDecisions(contractId: string) {
  const qc = useQueryClient();
  return useMutation<
    Awaited<ReturnType<typeof postDecisions>>,
    Error,
    DecisionsBody
  >({
    mutationFn: (body) => postDecisions(contractId, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.auditLog(contractId) });
    },
  });
}

/**
 * GET /api/contracts/{id}/audit-log.json. Polled at mount
 * time only — the audit log is append-only, so the cache is
 * fresh until a mutation invalidates it. The 5-minute
 * ``staleTime`` guards against a long-lived page going stale
 * silently.
 *
 * Retry behaviour: 4xx responses are NOT retried. A 404 means
 * "this contract has no audit log yet" (Build 3 hasn't
 * resumed its graph); retrying won't change that. 5xx and
 * network errors retry once with backoff.
 */
export function useAuditLog(contractId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.auditLog(contractId),
    queryFn: () => getAuditLogJson(contractId),
    enabled: enabled && Boolean(contractId),
    staleTime: 5 * 60 * 1000,
    retry: (failureCount, error) => {
      // Don't retry client errors (4xx). They are
      // deterministic: a missing contract id stays
      // missing, a malformed URL stays malformed.
      // 5xx and network errors get one retry.
      const status = (error as { status?: number } | undefined)?.status;
      if (status !== undefined && status >= 400 && status < 500) {
        return false;
      }
      return failureCount < 1;
    },
  });
}

/** GET /contracts/{id}/redline.docx as a Blob. */
export function useRedlineBlob(contractId: string, enabled = false) {
  return useQuery({
    queryKey: ["contract", contractId, "redline-blob"],
    queryFn: () => getRedlineDocx(contractId),
    enabled: enabled && Boolean(contractId),
    staleTime: Infinity, // blobs aren't reused; manual invalidation only
  });
}

/** Mutation wrapper for triggering a .docx download. */
export function useDownloadRedline() {
  return useMutation<Blob, Error, string>({
    mutationFn: (contractId) => getRedlineDocx(contractId),
  });
}

/** Mutation wrapper for triggering a PDF audit-log download. */
export function useDownloadAuditPdf() {
  return useMutation<Blob, Error, string>({
    mutationFn: (contractId) => getAuditLogPdf(contractId),
  });
}

// Re-export the adapter so callers don't have to import from
// ``@/lib/api`` directly.
export { spotResponseToReviewData };

// Re-export the per-decision type so consumers that only use
// the hooks file can build payloads without touching the API
// module.
export type { Decision, DecisionsBody, IngestResponse, SpotResponse };
