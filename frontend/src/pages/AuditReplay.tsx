import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { DisclaimerFooter } from "@/components/DisclaimerFooter";
import { AuditLogTimeline } from "@/components/AuditLogTimeline";
import { useAuditLog, useDownloadAuditPdf } from "@/lib/hooks";
import { downloadBlob } from "@/lib/api";

// AuditReplay — read-only timeline scrubber for a contract's
// audit log. The spec calls it "the audit replay view: at
// 14:32:08, the user approved flag #4 with severity override
// 2→1 and added context 'acceptable for our use case.'" The
// timeline component renders the rows; this page is the
// chrome (header, contract name, download buttons, error
// state, the "not legal advice" footer).
//
// URL: ``/contracts/{contractId}/audit`` — the contractId is
// the LangGraph thread id (also the audit log's
// ``contract_id`` field). The page reads it from the prop
// (the connected App shell handles the URL parse).
//
// Two download buttons:
// - "Download JSON" — uses the JSON endpoint; the file is
//   saved as ``<contract_id>-audit-log.json``.
// - "Download PDF" — uses the PDF endpoint; the file is
//   saved as ``<contract_id>-audit-log.pdf``.
//
// Both hit Build 4's endpoints
// (``/api/contracts/{id}/audit-log.{json,pdf}``).

export interface AuditReplayProps {
  /** The LangGraph thread id / contract id for the audit log. */
  contractId: string;
  /** Back-to-home navigation. */
  onBackToHome: () => void;
  /** Navigate to the live review page for this contract. */
  onBackToReview?: () => void;
}

export function AuditReplayPage({
  contractId,
  onBackToHome,
  onBackToReview,
}: AuditReplayProps) {
  const auditQuery = useAuditLog(contractId);
  const downloadPdf = useDownloadAuditPdf();

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
                <AuditLogTimeline rows={auditQuery.data} />
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
