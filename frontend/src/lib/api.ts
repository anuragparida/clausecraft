// Typed client for the Phase 3 backend endpoints.
//
// All paths are relative — the Vite dev proxy (see
// ``frontend/vite.config.ts``) routes ``/api/*`` to the FastAPI
// backend. In production a reverse proxy in front of both
// services does the same job.
//
// The client is intentionally small and explicit: one function
// per endpoint, no auto-generated OpenAPI types. Phase 3's
// endpoints are stable (Build 3 + Build 4 lock the contract via
// the e2e test in ``tests/phase3/test_e2e_three_contracts.py``)
// and a hand-rolled typed client is easier to read in code
// review than an OpenAPI codegen step.
//
// Conventions
// -----------
// - Every function returns a typed ``Promise``. On a non-2xx
//   response the promise rejects with an :class:`ApiError` that
//   carries the status + parsed body. The hooks layer
//   (``lib/hooks.ts``) turns that into a react-query error.
// - ``GET`` endpoints that return binary blobs (``.docx`` and
//   ``.pdf``) return ``Blob`` so the caller can hand them to
//   ``URL.createObjectURL`` for download. The audit-log JSON
//   endpoint returns parsed JSON.
// - The decisions payload mirrors what the e2e test sends
//   (``{decisions: [{clause_id, decision, ...}]}``). The backend
//   validates the ``decision`` enum server-side — the client
//   types prevent most drift but the backend is the source of
//   truth for the allowed values.

import type { Citation } from "@/components/CitationPopover";
import type { DeviationFlag, DeviationReviewData } from "@/pages/DeviationReview";

// --- Shared types ------------------------------------------------------

/**
 * One row of the contract's audit log. Mirrors the JSON shape
 * Build 4's ``GET /api/contracts/{id}/audit-log.json`` returns.
 *
 * The shape is intentionally permissive — the backend may add
 * new fields at any time and the audit-replay UI should not
 * crash on an unknown key. The fields listed here are the ones
 * the UI actually reads.
 */
export interface AuditLogRow {
  contract_id: string;
  clause_id: string;
  decision_type: string;
  payload_json: Record<string, unknown>;
  decided_by: string;
  decided_at: string; // ISO-8601
}

/**
 * The decision a user can submit for a single flag. Mirrors the
 * shape Build 3's resume endpoint accepts in the
 * ``decisions[]`` array.
 *
 * Field semantics
 * ---------------
 * - ``"approve"`` — accept the flag; the drafter will produce a
 *   redline for this clause.
 * - ``"reject"`` — dismiss the flag; no redline.
 * - ``"edit_severity"`` — change the spotter's severity score;
 *   ``new_severity`` (and optionally ``old_severity``) must be
 *   set. The backend will write a ``severity_edited`` audit
 *   event.
 * - ``"add_context"`` — attach a free-form rationale to the
 *   flag; ``context`` must be set. The backend will write a
 *   ``context_added`` audit event.
 */
export type DecisionAction =
  | "approve"
  | "reject"
  | "edit_severity"
  | "add_context";

export interface Decision {
  clause_id: string;
  decision: DecisionAction;
  /** Required for ``edit_severity``. 0..3. */
  new_severity?: number;
  /** Optional, helps the audit log narrate the change. 0..3. */
  old_severity?: number;
  /** Required for ``add_context``; the user's free-form note. */
  context?: string;
}

/** Body of the resume call. */
export interface DecisionsBody {
  decisions: Decision[];
}

// --- Errors ------------------------------------------------------------

/**
 * Raised when the backend returns a non-2xx response. The
 * ``status`` and ``body`` are preserved so the UI can render a
 * useful error message.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;
  readonly url: string;

  constructor(url: string, status: number, body: unknown) {
    const message =
      typeof body === "object" && body !== null && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `HTTP ${status} from ${url}`;
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
    this.url = url;
  }
}

async function readErrorBody(res: Response): Promise<unknown> {
  const ct = res.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) {
    try {
      return await res.json();
    } catch {
      return null;
    }
  }
  try {
    return await res.text();
  } catch {
    return null;
  }
}

async function request<T>(
  url: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await readErrorBody(res);
    throw new ApiError(url, res.status, body);
  }
  // 204 No Content
  if (res.status === 204) {
    return undefined as T;
  }
  const ct = res.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) {
    return (await res.json()) as T;
  }
  return (await res.text()) as unknown as T;
}

// --- Endpoint: ingest --------------------------------------------------
//
// Phase 1 endpoint, exposed unchanged in Phase 3. Takes a
// multipart upload and returns the typed clause list. Build 3's
// flow eventually drives this same endpoint when the UI starts
// a new review; the new ``contract_id`` the backend returns
// becomes the LangGraph thread id.

export interface IngestResponse {
  filename: string;
  clauses: Array<{
    id: string;
    type: string;
    text: string;
    language: string;
    confidence: number;
    position?: Record<string, unknown>;
  }>;
  is_scanned?: boolean;
  scanned_warning?: string | null;
  /** Phase 3 — Build 3 may echo a server-generated contract id. */
  contract_id?: string;
}

export async function postIngest(
  file: File,
  language: "en" | "de" = "en",
): Promise<IngestResponse> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("language", language);
  return request<IngestResponse>("/api/contracts/ingest", {
    method: "POST",
    body: fd,
  });
}

// --- Endpoint: spot ----------------------------------------------------
//
// Phase 2 endpoint, exposed unchanged in Phase 3. Takes a
// classified clause list and returns the deviation table.

export interface SpotResponse {
  filename: string;
  flag_count: number;
  flagged_count: number;
  unverified_count: number;
  no_baseline_count: number;
  matrix_version: string;
  embedding_provider: string;
  flags: Array<{
    clause_id: string;
    score: number;
    rationale: string;
    citation: Citation | null;
    unverified: boolean;
    baseline_type: string;
  }>;
}

/** Adapter: turn a SpotResponse into the DeviationReviewData shape. */
export function spotResponseToReviewData(r: SpotResponse): DeviationReviewData {
  const flags: DeviationFlag[] = r.flags.map((f) => ({
    clause_id: f.clause_id,
    score: f.score,
    rationale: f.rationale,
    citation: f.citation,
    unverified: f.unverified,
    baseline_type: f.baseline_type,
  }));
  return {
    filename: r.filename,
    flag_count: r.flag_count,
    flagged_count: r.flagged_count,
    unverified_count: r.unverified_count,
    no_baseline_count: r.no_baseline_count,
    matrix_version: r.matrix_version,
    embedding_provider: r.embedding_provider,
    flags,
  };
}

export async function postSpot(payload: {
  filename: string;
  clauses: IngestResponse["clauses"];
}): Promise<SpotResponse> {
  return request<SpotResponse>("/api/contracts/spot", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// --- Endpoint: decisions (Build 3 resume) ------------------------------
//
// POST the per-flag decision batch. The backend's resume path
// (LangGraph ``Command``) reads this and continues the graph
// from the interrupt node. Returns the resumed state summary.

export interface DecisionsResponse {
  /** Whether the graph accepted the resume and ran to END. */
  ok: boolean;
  /** Total audit events written for the contract so far. */
  audit_event_count?: number;
  /** Any error the graph captured (per the state.error field). */
  error?: string | null;
  /** Path the caller can hit to download the .docx. */
  redline_path?: string;
}

export async function postDecisions(
  contractId: string,
  body: DecisionsBody,
): Promise<DecisionsResponse> {
  return request<DecisionsResponse>(
    `/api/contracts/${encodeURIComponent(contractId)}/decisions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

// --- Endpoint: redline.docx download (Build 2/3) ----------------------

/**
 * Download the redline .docx as a Blob. The caller is expected
 * to call ``URL.createObjectURL`` and trigger a download with a
 * sensible filename. We return a ``Blob`` (not a parsed
 * document) so the caller can decide whether to feed it to
 * mammoth.js for the preview, or hand it to the file-saver.
 */
export async function getRedlineDocx(contractId: string): Promise<Blob> {
  const res = await fetch(
    `/api/contracts/${encodeURIComponent(contractId)}/redline.docx`,
  );
  if (!res.ok) {
    const body = await readErrorBody(res);
    throw new ApiError(
      `/api/contracts/${contractId}/redline.docx`,
      res.status,
      body,
    );
  }
  return res.blob();
}

// --- Endpoint: redline.md download (Build 5) ---------------------------

/**
 * Download the redline as a markdown-diff ``Blob``. The
 * markdown path is the v0 escape hatch for users who cannot
 * open the .docx in Word — it is the same contract text +
 * accepted proposals, expressed as a unified diff. The
 * backend renders the markdown from the same state the
 * .docx was rendered from, so the two outputs are consistent.
 *
 * Returns a ``Blob`` (``text/markdown; charset=utf-8``). The
 * caller hands the blob to ``downloadBlob`` with a sensible
 * filename. We do not cache the blob because the .md path
 * is rare and the bytes are small.
 */
export async function getRedlineMarkdown(contractId: string): Promise<Blob> {
  const res = await fetch(
    `/api/contracts/${encodeURIComponent(contractId)}/redline.md`,
  );
  if (!res.ok) {
    const body = await readErrorBody(res);
    throw new ApiError(
      `/api/contracts/${contractId}/redline.md`,
      res.status,
      body,
    );
  }
  return res.blob();
}

// --- Endpoint: audit-log (Build 4) ------------------------------------

/**
 * Fetch the audit log as a parsed JSON array. The backend may
 * return either a top-level array (the natural FastAPI
 * ``JSONResponse`` shape) or a ``{events: [...]}`` envelope.
 * We accept both and always return the array.
 */
export async function getAuditLogJson(
  contractId: string,
): Promise<AuditLogRow[]> {
  const res = await fetch(
    `/api/contracts/${encodeURIComponent(contractId)}/audit-log.json`,
  );
  if (!res.ok) {
    const body = await readErrorBody(res);
    throw new ApiError(
      `/api/contracts/${contractId}/audit-log.json`,
      res.status,
      body,
    );
  }
  const decoded = (await res.json()) as unknown;
  if (Array.isArray(decoded)) {
    return decoded as AuditLogRow[];
  }
  if (
    typeof decoded === "object" &&
    decoded !== null &&
    Array.isArray((decoded as { events?: unknown }).events)
  ) {
    return (decoded as { events: AuditLogRow[] }).events;
  }
  throw new ApiError(
    `/api/contracts/${contractId}/audit-log.json`,
    200,
    "audit-log response is neither a list nor a {events:[]} envelope",
  );
}

/**
 * Download the audit-log PDF as a Blob. The caller hands the
 * blob to a download link.
 */
export async function getAuditLogPdf(contractId: string): Promise<Blob> {
  const res = await fetch(
    `/api/contracts/${encodeURIComponent(contractId)}/audit-log.pdf`,
  );
  if (!res.ok) {
    const body = await readErrorBody(res);
    throw new ApiError(
      `/api/contracts/${contractId}/audit-log.pdf`,
      res.status,
      body,
    );
  }
  return res.blob();
}

// --- Helpers -----------------------------------------------------------

/**
 * Trigger a browser download for a Blob with a filename. Works
 * in every modern browser; no DOMPurify / file-saver dep
 * needed.
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Revoke after a tick so the browser has time to start the
  // download. The exact timeout is a heuristic — too short
  // and the download aborts on some browsers, too long and
  // the URL lingers.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
