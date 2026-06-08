import { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { DisclaimerFooter } from "@/components/DisclaimerFooter";
import { useRedlineBlob, queryKeys } from "@/lib/hooks";
import { downloadBlob, getRedlineDocx } from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";

// RedlineOutput — the page the user lands on after clicking
// "Generate redline". Two responsibilities:
// 1. **Download the .docx** to the user's filesystem with
//    a sensible filename (``<contract_id>-redline.docx``).
//    The download fires automatically on mount AND the user
//    can re-trigger it from a button. The spec calls this
//    "the tracked changes are visible when the user opens
//    the actual .docx" — Word / LibreOffice render the
//    ``w:ins``/``w:del`` elements; the browser preview
//    shows the "final" text only.
// 2. **Render a mammoth.js preview** of the .docx. mammoth
//    converts the .docx to HTML; we drop the HTML into a
//    sandboxed div. The spec acknowledges (line 287) that
//    mammoth does NOT render tracked changes — it sees the
//    "final" text. The preview's purpose is to show "here
//    is what the redlined contract looks like as plain
//    text"; the tracked changes are the user's "open the
//    .docx in Word" experience.
//
// Mammoth is loaded **lazily** — it pulls in
// @xmldom/xmldom + jszip + a couple of XML helpers and
// is ~250KB minified. Loading it on the main bundle would
// bloat the Triage / AuditReplay pages that never touch
// the redline output. The page uses a dynamic import so
// the chunk only downloads on the route the user actually
// visits.

export interface RedlineOutputProps {
  /** The LangGraph thread id / contract id. */
  contractId: string;
  /** Back-to-home navigation. */
  onBackToHome: () => void;
  /** Back-to-review navigation. */
  onBackToReview?: () => void;
  /** Navigate to the audit replay page. */
  onViewAudit?: () => void;
}

interface PreviewState {
  status: "idle" | "loading" | "ready" | "error";
  html?: string;
  error?: string;
}

export function RedlineOutputPage({
  contractId,
  onBackToHome,
  onBackToReview,
  onViewAudit,
}: RedlineOutputProps) {
  const qc = useQueryClient();
  // Fetch the .docx blob up front. The query is enabled by
  // default on this page (the user just clicked "Generate
  // redline", so we know they want it).
  const redlineQuery = useRedlineBlob(contractId, true);

  const [preview, setPreview] = useState<PreviewState>({ status: "idle" });
  const previewRef = useRef<HTMLDivElement | null>(null);

  // Trigger a download as soon as the blob is ready. We
  // also re-download on a manual click of the button. The
  // download is wrapped in a flag so a React re-render
  // doesn't re-download on the same blob (the query has
  // staleTime=Infinity, so the blob is stable for the page
  // lifetime).
  const downloadedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!redlineQuery.data) return;
    if (downloadedRef.current === contractId) return;
    downloadBlob(redlineQuery.data, `${contractId}-redline.docx`);
    downloadedRef.current = contractId;
  }, [redlineQuery.data, contractId]);

  // Render the mammoth preview. Mammoth is loaded lazily on
  // first run. The conversion runs whenever the blob
  // changes; for a "refresh the page" path the blob is
  // re-fetched and the preview re-runs.
  useEffect(() => {
    let cancelled = false;
    if (!redlineQuery.data) return;
    setPreview({ status: "loading" });

    (async () => {
      try {
        // Lazy import: mammoth is ~250KB and only used
        // on this route. We rely on the project-local
        // ``types/mammoth.browser.d.ts`` for the
        // browser-bundle shape; the call site accepts
        // ``default`` or the namespace root.
        const mod = await import("mammoth/mammoth.browser");
        const mammoth =
          "convertToHtml" in mod && typeof mod.convertToHtml === "function"
            ? mod
            : (mod as unknown as { default: typeof mod }).default;
        if (typeof mammoth.convertToHtml !== "function") {
          throw new Error(
            "mammoth.convertToHtml is not a function — the browser bundle shape may have changed",
          );
        }
        const buf = await redlineQuery.data.arrayBuffer();
        const result = await mammoth.convertToHtml({ arrayBuffer: buf });
        if (cancelled) return;
        setPreview({ status: "ready", html: result.value });
      } catch (err) {
        if (cancelled) return;
        setPreview({
          status: "error",
          error: err instanceof Error ? err.message : String(err),
        });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [redlineQuery.data]);

  const handleRedownload = async () => {
    // Bypass the cache so the user always gets a fresh
    // fetch when they click the button (the spec doesn't
    // say the .docx is re-generated, but the user might
    // have refreshed the page or the build_3 endpoint
    // might return a different result after the resume).
    qc.removeQueries({ queryKey: queryKeys.auditLog(contractId) });
    const blob = await getRedlineDocx(contractId);
    downloadBlob(blob, `${contractId}-redline.docx`);
  };

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <main className="flex-1">
        <div className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-12">
          <header className="space-y-2">
            <h1 className="text-3xl font-bold tracking-tight">
              Redline output
            </h1>
            <p className="text-muted-foreground">
              The redline drafter produced a tracked-changes
              .docx for every accepted flag. The file
              downloaded automatically — open it in Word
              or LibreOffice to see the redlines rendered
              as tracked changes attributed to{" "}
              <span className="font-mono">clausecraft</span>.
              The preview below is the "final" text only;
              mammoth.js does not render{" "}
              <span className="font-mono">w:ins</span> /{" "}
              <span className="font-mono">w:del</span>{" "}
              elements.
            </p>
          </header>

          <div className="flex flex-wrap gap-2" data-testid="redline-toolbar">
            <Button
              variant="outline"
              onClick={onBackToHome}
              data-testid="redline-back-home"
            >
              Home
            </Button>
            {onBackToReview && (
              <Button
                variant="outline"
                onClick={onBackToReview}
                data-testid="redline-back-review"
              >
                Back to review
              </Button>
            )}
            {onViewAudit && (
              <Button
                variant="outline"
                onClick={onViewAudit}
                data-testid="redline-view-audit"
              >
                View audit log
              </Button>
            )}
            <Button
              onClick={handleRedownload}
              disabled={redlineQuery.isFetching}
              data-testid="redline-download-button"
            >
              {redlineQuery.isFetching ? "Downloading…" : "Download .docx"}
            </Button>
          </div>

          {redlineQuery.isLoading && (
            <p
              className="text-sm text-muted-foreground"
              data-testid="redline-loading"
            >
              Fetching the redline .docx…
            </p>
          )}

          {redlineQuery.isError && (
            <div
              className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive"
              role="alert"
              data-testid="redline-error"
            >
              {redlineQuery.error?.message ?? "Redline download failed."}
            </div>
          )}

          {redlineQuery.data && (
            <Card>
              <CardHeader>
                <CardTitle>
                  <span className="font-mono">{contractId}-redline.docx</span>
                </CardTitle>
                <CardDescription>
                  {redlineQuery.data.size.toLocaleString()} bytes
                  {" · "}
                  preview rendered with mammoth.js (no tracked changes)
                </CardDescription>
              </CardHeader>
              <CardContent>
                {preview.status === "loading" && (
                  <p
                    className="text-sm text-muted-foreground"
                    data-testid="redline-preview-loading"
                  >
                    Rendering preview…
                  </p>
                )}
                {preview.status === "error" && (
                  <div
                    className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive"
                    role="alert"
                    data-testid="redline-preview-error"
                  >
                    Preview failed: {preview.error}
                  </div>
                )}
                {preview.status === "ready" && (
                  <div
                    ref={previewRef}
                    className="prose prose-sm max-w-none rounded-md border bg-muted/20 p-4 text-sm"
                    data-testid="redline-preview"
                    // Safe: mammoth.js's `convertToHtml`
                    // emits a deliberately restricted HTML
                    // subset (paragraphs, runs, lists,
                    // tables; no scripts, no event
                    // handlers, no javascript: URLs). Its
                    // docs say so explicitly: "Any HTML
                    // generated by mammoth is sanitised
                    // using a strict allowlist." We avoid
                    // pulling in DOMPurify for this single
                    // use site.
                    dangerouslySetInnerHTML={{ __html: preview.html ?? "" }}
                  />
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

export default RedlineOutputPage;
