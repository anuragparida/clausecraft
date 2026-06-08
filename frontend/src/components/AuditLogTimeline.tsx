import { cn } from "@/lib/utils";
import type { AuditLogRow } from "@/lib/api";

// AuditLogTimeline — vertical timeline of audit events for
// one contract. Read-only. Renders one row per ``AuditLogRow``
// with the timestamp, decision type, and the relevant payload
// fields surfaced as a "what happened" sentence.
//
// Why a custom component (not shadcn / Radix timeline)
// -----------------------------------------------------
// Phase 3 only needs the timeline on the audit-replay page
// and the future audit-log PDF export. A 100-line component
// is easier to style + test than a shadcn registry install
// that drags in Radix + Tailwind-merge + a half-dozen
// variants. The data shape is small (timestamp, type,
// payload) — no need for virtualization on a 3-contract
// demo.

// --- Pretty-printing helpers -------------------------------------------

/** Map a decision_type to a short, human-friendly verb. */
function decisionTypeLabel(type: string): string {
  switch (type) {
    case "graph_started":
      return "Pipeline started";
    case "graph_resumed":
      return "Pipeline resumed";
    case "flag_accepted":
      return "Flag accepted";
    case "flag_rejected":
      return "Flag rejected";
    case "severity_edited":
      return "Severity edited";
    case "context_added":
      return "Context added";
    case "redline_generated":
      return "Redline generated";
    case "redline_downloaded":
      return "Redline downloaded";
    default:
      // Unknown / future decision types: render the raw
      // value so the timeline is still informative.
      return type.replace(/_/g, " ");
  }
}

/** A short dot color per decision type. */
function decisionTypeTone(type: string): "default" | "success" | "warning" | "danger" | "muted" {
  switch (type) {
    case "graph_started":
    case "graph_resumed":
    case "redline_generated":
    case "redline_downloaded":
      return "muted";
    case "flag_accepted":
      return "success";
    case "flag_rejected":
      return "danger";
    case "severity_edited":
    case "context_added":
      return "warning";
    default:
      return "default";
  }
}

function formatTimestamp(iso: string): string {
  if (!iso) return "—";
  // The backend writes ISO-8601 (typically with a Z suffix).
  // We use the browser's ``Date`` parser; the spec doesn't
  // pin a timezone and the audit log is single-operator,
  // so a local-time render is fine.
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

/** Build a one-sentence summary from a row's payload. */
function payloadSummary(row: AuditLogRow): string {
  const p = row.payload_json ?? {};
  switch (row.decision_type) {
    case "graph_started":
      return typeof p.clause_count === "number"
        ? `Parsed ${p.clause_count} clause${p.clause_count === 1 ? "" : "s"}.`
        : "Pipeline started.";
    case "graph_resumed":
      return "Pipeline resumed after human review.";
    case "flag_accepted":
      return row.clause_id
        ? `User approved flag on clause ${row.clause_id}.`
        : "User approved a flag.";
    case "flag_rejected":
      return row.clause_id
        ? `User rejected flag on clause ${row.clause_id}.`
        : "User rejected a flag.";
    case "severity_edited":
      return row.clause_id
        ? `User changed severity on clause ${row.clause_id}${
            p.new_severity !== undefined && p.old_severity !== undefined
              ? ` (${p.old_severity} → ${p.new_severity}).`
              : "."
          }`
        : "User changed a severity score.";
    case "context_added":
      return row.clause_id
        ? `User attached context to clause ${row.clause_id}: "${p.context ?? ""}"`
        : "User attached context.";
    case "redline_generated":
      return typeof p.accepted_count === "number"
        ? `Drafter produced ${p.accepted_count} redline proposal${p.accepted_count === 1 ? "" : "s"}.`
        : "Drafter produced redline proposals.";
    case "redline_downloaded":
      return "User downloaded the redline .docx.";
    default:
      // Fallback: stringify the payload so the user sees
      // something rather than a blank row.
      try {
        return JSON.stringify(p);
      } catch {
        return "";
      }
  }
}

// --- Component ---------------------------------------------------------

export interface AuditLogTimelineProps {
  rows: AuditLogRow[];
  /** Optional CSS class for the outer container. */
  className?: string;
  /**
   * When true, render a header line with the row count.
   * The audit-replay page flips this on; the PDF export
   * (Build 4) renders the timeline without the header.
   */
  showHeader?: boolean;
}

export function AuditLogTimeline({
  rows,
  className,
  showHeader = true,
}: AuditLogTimelineProps) {
  if (rows.length === 0) {
    return (
      <div
        className={cn("text-sm text-muted-foreground", className)}
        data-testid="audit-timeline-empty"
      >
        No audit events yet for this contract. The timeline
        populates as the pipeline runs and you make decisions.
      </div>
    );
  }

  // Sort: oldest first. The backend writes events in
  // append-only order so the rows are *probably* already
  // sorted, but we don't rely on that — a future migration
  // could backfill old rows.
  const sorted = [...rows].sort((a, b) => {
    const ta = Date.parse(a.decided_at);
    const tb = Date.parse(b.decided_at);
    if (Number.isNaN(ta) || Number.isNaN(tb)) return 0;
    return ta - tb;
  });

  return (
    <div className={cn("space-y-2", className)} data-testid="audit-timeline">
      {showHeader && (
        <p
          className="text-xs text-muted-foreground"
          data-testid="audit-timeline-header"
        >
          {rows.length} audit event{rows.length === 1 ? "" : "s"} for this
          contract.
        </p>
      )}
      <ol className="relative ml-2 border-l border-border">
        {sorted.map((row, idx) => {
          const tone = decisionTypeTone(row.decision_type);
          return (
            <li
              key={`${row.decided_at}-${idx}`}
              className="ml-4 py-3"
              data-testid="audit-timeline-row"
              data-decision-type={row.decision_type}
            >
              {/* The dot on the timeline. */}
              <span
                className={cn(
                  "absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full border-2 border-background",
                  tone === "success" && "bg-emerald-500",
                  tone === "warning" && "bg-amber-500",
                  tone === "danger" && "bg-red-500",
                  tone === "muted" && "bg-slate-400",
                  tone === "default" && "bg-blue-500",
                )}
                aria-hidden
                data-testid="audit-timeline-dot"
              />
              <div className="flex flex-col gap-0.5">
                <span
                  className="text-sm font-medium"
                  data-testid="audit-timeline-decision-type"
                >
                  {decisionTypeLabel(row.decision_type)}
                </span>
                <span
                  className="text-xs text-muted-foreground"
                  data-testid="audit-timeline-timestamp"
                >
                  {formatTimestamp(row.decided_at)}
                  {row.decided_by && (
                    <>
                      {" · "}
                      <span
                        className="font-mono"
                        data-testid="audit-timeline-actor"
                      >
                        {row.decided_by}
                      </span>
                    </>
                  )}
                </span>
                <span
                  className="mt-1 text-xs"
                  data-testid="audit-timeline-summary"
                >
                  {payloadSummary(row)}
                </span>
                {row.clause_id && (
                  <span
                    className="font-mono text-[11px] text-muted-foreground"
                    data-testid="audit-timeline-clause-id"
                  >
                    clause: {row.clause_id}
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export default AuditLogTimeline;
