import { useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { DisclaimerFooter } from "@/components/DisclaimerFooter";
import { AuditLogTimeline } from "@/components/AuditLogTimeline";
import { useAuditLog, useDownloadAuditPdf } from "@/lib/hooks";
import { downloadBlob } from "@/lib/api";
import type { AuditLogRow } from "@/lib/api";

// AuditReplay — read-only timeline scrubber for a contract's
// audit log. The spec calls it "the audit replay view: at
// 14:32:08, the user approved flag #4 with severity override
// 2→1 and added context 'acceptable for our use case.'"
//
// Build 5 implements three of the spec's UX requirements on
// this page:
//
// 1. **Narrative rows.** Every event the timeline renders is
//    also described in the spec's voice ("At HH:MM:SS, the
//    user …"). The ``AuditLogTimeline`` component already
//    produces a one-sentence ``payloadSummary`` per row;
//    the spec phrasing is rendered in the row's plain-text
//    summary line.
//
// 2. **Timeline scrubber.** A range slider at the top of the
//    page, bounded by ``min(decided_at)`` and
//    ``max(decided_at)`` across the full row set. Drag the
//    right handle left to filter the visible timeline to
//    only the events that happened before the chosen
//    timestamp. The full row count is still visible in the
//    header so the user knows the slider is filtering.
//
// 3. **Clickable rows that expand.** Every row has a small
//    "show payload" disclosure. When toggled, the row grows
//    to include the raw ``payload_json`` as a pretty-printed
//    JSON block. The disclosure is per-row and not
//    exclusive; the user can expand as many rows as they
//    want at once.
//
// Two download buttons:
// - "Download JSON" — uses the JSON endpoint; the file is
//   saved as ``<contract_id>-audit-log.json``.
// - "Download PDF" — uses the PDF endpoint; the file is
//   saved as ``<contract_id>-audit-log.pdf``.
//
// Both hit Build 4's endpoints
// (``/api/contracts/{id}/audit-log.{json,pdf}``).
//
// URL: ``/contracts/{contractId}/audit`` — the contractId is
// the LangGraph thread id (also the audit log's
// ``contract_id`` field). The page reads it from the prop
// (the connected App shell handles the URL parse).

export interface AuditReplayProps {
  /** The LangGraph thread id / contract id for the audit log. */
  contractId: string;
  /** Back-to-home navigation. */
  onBackToHome: () => void;
  /** Navigate to the live review page for this contract. */
  onBackToReview?: () => void;
}

/** Convert an ISO-8601 timestamp into a unix-ms epoch. */
function tsToMs(iso: string): number {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? 0 : t;
}

/** Format a unix-ms epoch as the local HH:MM:SS used by the scrubber. */
function msToHms(ms: number): string {
  const d = new Date(ms);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

export function AuditReplayPage({
  contractId,
  onBackToHome,
  onBackToReview,
}: AuditReplayProps) {
  const auditQuery = useAuditLog(contractId);
  const downloadPdf = useDownloadAuditPdf();
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());

  // Compute the scrubber bounds from the full row set. The
  // slider's range is the unix-ms span between the oldest
  // and newest event; the user drags the right handle to
  // filter rows whose ``decided_at`` is at or before the
  // chosen timestamp.
  const { minMs, maxMs } = useMemo(() => {
    const rows = auditQuery.data ?? [];
    if (rows.length === 0) return { minMs: 0, maxMs: 0 };
    let lo = Infinity;
    let hi = -Infinity;
    for (const r of rows) {
      const t = tsToMs(r.decided_at);
      if (t < lo) lo = t;
      if (t > hi) hi = t;
    }
    return { minMs: lo, maxMs: hi };
  }, [auditQuery.data]);

  // The scrubber is only meaningful when there is a real
  // span to filter over. A single-row or empty log falls
  // back to "no scrubber" (the slider is hidden, all rows
  // are visible).
  const canScrub = maxMs > minMs;

  // Default: scrubber pinned to the right edge (newest
  // event). The user drags left to narrow the visible
  // window.
  const [scrubAt, setScrubAt] = useState<number | null>(null);
  const effectiveScrub = scrubAt ?? maxMs;

  // Filter the rows by the scrubber. Rows with no parseable
  // timestamp fall through (always visible) — the audit
  // log writer should never produce those, but we don't
  // want a malformed row to hide the whole timeline.
  const visibleRows: AuditLogRow[] = useMemo(() => {
    const rows = auditQuery.data ?? [];
    if (!canScrub || scrubAt === null) return rows;
    return rows.filter((r) => {
      const t = tsToMs(r.decided_at);
      if (t === 0) return true;
      return t <= effectiveScrub;
    });
  }, [auditQuery.data, canScrub, scrubAt, effectiveScrub]);

  const toggleRow = (idx: number) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) {
        next.delete(idx);
      } else {
        next.add(idx);
      }
      return next;
    });
  };

  const handleDownloadJson = () => {
    const rows = auditQuery.data ?? [];
    const blob = new Blob([JSON.stringify(rows, null, 2)], {
      type: "application/json",
    });
    downloadBlob(blob, `${contractId}-audit-log.json`);
  };

  const handleDownloadPdf = async () => {
    const blob = await downloadPdf.mutateAsync(contractId);
    downloadBlob(blob, `${contractId}-audit-log.pdf`);
  };

  // Reset the scrubber when the user clicks "Reset" — this
  // is the only way to get back to the full timeline view
  // without re-loading the page.
  const handleResetScrub = () => setScrubAt(null);

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <main className="flex-1">
        <div className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-12">
          <header className="space-y-2">
            <h1 className="text-3xl font-bold tracking-tight">
              Audit replay
            </h1>
            <p className="text-muted-foreground">
              The full decision chain for this contract, in
              the order it was written to the append-only
              audit log. Every approval, rejection, severity
              edit, context add, redline generation, and
              download is recorded. The table is read-only —
              it is the regulator's eye, not a place to
              revisit decisions.
            </p>
          </header>

          <div className="flex flex-wrap gap-2" data-testid="audit-replay-toolbar">
            <Button
              variant="outline"
              onClick={onBackToHome}
              data-testid="audit-back-home"
            >
              Home
            </Button>
            {onBackToReview && (
              <Button
                variant="outline"
                onClick={onBackToReview}
                data-testid="audit-back-review"
              >
                Back to review
              </Button>
            )}
            <Button
              variant="outline"
              onClick={handleDownloadJson}
              disabled={!auditQuery.data || auditQuery.data.length === 0}
              data-testid="audit-download-json"
            >
              Download JSON
            </Button>
            <Button
              variant="outline"
              onClick={handleDownloadPdf}
              disabled={downloadPdf.isPending}
              data-testid="audit-download-pdf"
            >
              {downloadPdf.isPending ? "Downloading…" : "Download PDF"}
            </Button>
          </div>

          {/* Timeline scrubber. A range slider bounded by
              min/max decided_at. The visible window is the
              rows whose decided_at is at or before the
              scrubber handle. */}
          {canScrub && (
            <div
              className="flex flex-col gap-2 rounded-md border bg-muted/20 p-3"
              data-testid="audit-scrubber"
            >
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>
                  Scrub from <span className="font-mono">{msToHms(minMs)}</span>
                  {" "}to{" "}
                  <span className="font-mono" data-testid="audit-scrub-current">
                    {msToHms(effectiveScrub)}
                  </span>
                  {" "}(
                  {visibleRows.length}
                  {" "}of {auditQuery.data?.length ?? 0} events)
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={handleResetScrub}
                  disabled={scrubAt === null}
                  data-testid="audit-scrub-reset"
                >
                  Reset
                </Button>
              </div>
              <input
                type="range"
                min={minMs}
                max={maxMs}
                step={1000}
                value={effectiveScrub}
                onChange={(e) => setScrubAt(Number(e.target.value))}
                className="w-full"
                data-testid="audit-scrub-slider"
                aria-label="Filter audit log by timestamp"
              />
            </div>
          )}

          {auditQuery.isLoading && (
            <p
              className="text-sm text-muted-foreground"
              data-testid="audit-loading"
            >
              Loading audit log…
            </p>
          )}

          {auditQuery.isError && (
            <div
              className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive"
              role="alert"
              data-testid="audit-error"
            >
              {auditQuery.error?.message ?? "Audit log fetch failed."}
            </div>
          )}

          {auditQuery.data && (
            <Card>
              <CardHeader>
                <CardTitle>
                  <span className="font-mono">{contractId}</span>
                </CardTitle>
                <CardDescription>
                  Append-only. Every event has a server-set
                  timestamp and a ``decided_by`` actor.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <AuditLogTimeline
                  rows={visibleRows}
                  compact={false}
                />
                {/* Per-row disclosure: each row can be
                    expanded to reveal the full payload_json.
                    We re-render the rows as a sibling list
                    so the disclosure state is owned by the
                    page (not the timeline component, which
                    stays a pure timeline render). */}
                {visibleRows.length > 0 && (
                  <ol
                    className="mt-4 flex flex-col gap-1"
                    data-testid="audit-row-disclosures"
                  >
                    {visibleRows.map((row, idx) => {
                      const expanded = expandedRows.has(idx);
                      return (
                        <li
                          key={`disclosure-${row.decided_at}-${idx}`}
                          className="rounded-md border bg-background"
                          data-testid={`audit-row-disclosure-${idx}`}
                          data-expanded={expanded ? "true" : "false"}
                        >
                          <button
                            type="button"
                            onClick={() => toggleRow(idx)}
                            className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs hover:bg-muted/40"
                            data-testid={`audit-row-toggle-${idx}`}
                            aria-expanded={expanded}
                          >
                            <span className="font-mono">
                              {row.decision_type} · {row.decided_at}
                            </span>
                            <span className="text-muted-foreground">
                              {expanded ? "▾ hide payload" : "▸ show payload"}
                            </span>
                          </button>
                          {expanded && (
                            <pre
                              className="overflow-x-auto border-t bg-muted/20 px-3 py-2 text-[11px] leading-relaxed"
                              data-testid={`audit-row-payload-${idx}`}
                            >
                              {JSON.stringify(row.payload_json, null, 2)}
                            </pre>
                          )}
                        </li>
                      );
                    })}
                  </ol>
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

export default AuditReplayPage;
