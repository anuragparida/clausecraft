import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  getRecentContracts,
  type ContractSummary,
  ApiError,
} from "@/lib/api";

// RecentContractsCard — Phase 6 home grid card.
//
// Renders a list of the most recently-touched contracts
// in the in-memory backend store. Clicking a row (or its
// "Open review" button) navigates to ``/contracts/{id}/review``,
// which is the connected review page Phase 3 built.
//
// Why this lives in its own component
// ----------------------------------
// The home grid has 6 cards today; the "Recent" slot is the
// only one that needs a fetch-on-mount. Putting the fetch
// + render logic in App.tsx would bloat the home view and
// make the layout changes in sibling cards harder to review.
// The component also owns the relative-time formatter
// (``formatRelativeTime``) — a private helper that doesn't
// belong in the global lib.
//
// Empty / loading / error states
// ------------------------------
// - Loading: a skeleton row with the same height as a real row.
// - Empty: "No contracts yet — triage one to see it here."
// - Error: the message inline; the card stays visible (the
//   rest of the home page is unaffected).

// --- Relative-time formatter -------------------------------------------

/**
 * Format an ISO-8601 UTC timestamp as a short relative
 * string ("just now", "5 min ago", "2 days ago").
 *
 * Falls back to the raw timestamp when the input is
 * malformed / unparseable. We don't pull in
 * ``date-fns`` / ``dayjs`` for one helper — the home
 * card is a portfolio page, not a Slack channel.
 */
function formatRelativeTime(iso: string): string {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return iso;
  const diffMs = Date.now() - then.getTime();
  if (diffMs < 0) return "just now"; // clock skew — treat as "now"
  const sec = Math.floor(diffMs / 1000);
  if (sec < 30) return "just now";
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} min ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} hr ago`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day} day${day === 1 ? "" : "s"} ago`;
  // For older rows we drop back to the absolute date so
  // the relative-time text stays short.
  return then.toISOString().slice(0, 10);
}

// --- Pipeline-stage label ---------------------------------------------

/**
 * Resolve a row's pipeline booleans to a short, human label.
 *
 * The booleans are an unordered set (a contract can be in
 * spot + decisions at the same time, etc.); we pick the
 * most-advanced stage. The label is shown in the row's
 * right-hand column.
 */
function pipelineStageLabel(row: ContractSummary): string {
  if (row.has_redline) return "Redline ready";
  if (row.has_decisions) return "Decisions in";
  if (row.has_spot) return "Spotted";
  if (row.has_ingest) return "Ingested";
  return "Empty";
}

// --- Component ---------------------------------------------------------

export interface RecentContractsCardProps {
  /** Called when the user clicks a row / "Open review". */
  onOpenContract: (contractId: string) => void;
}

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; rows: ContractSummary[] }
  | { kind: "error"; message: string };

export function RecentContractsCard({
  onOpenContract,
}: RecentContractsCardProps) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    getRecentContracts()
      .then((rows) => {
        if (cancelled) return;
        setState({ kind: "ready", rows });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError
            ? `${err.status}: ${err.message}`
            : err instanceof Error
              ? err.message
              : "Failed to load recent contracts.";
        setState({ kind: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Card data-testid="home-recent-card">
      <CardHeader>
        <CardTitle>Recent contracts</CardTitle>
        <CardDescription>
          Contracts you have touched in this server process.
          Click a row to jump straight into the review.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {state.kind === "loading" && (
          <div
            data-testid="home-recent-loading"
            className="text-sm text-muted-foreground"
          >
            Loading recent contracts…
          </div>
        )}
        {state.kind === "error" && (
          <div
            data-testid="home-recent-error"
            className="text-sm text-destructive"
            role="alert"
          >
            Could not load recent contracts: {state.message}
          </div>
        )}
        {state.kind === "ready" && state.rows.length === 0 && (
          <div
            data-testid="home-recent-empty"
            className="text-sm text-muted-foreground"
          >
            No contracts yet — triage one to see it here.
          </div>
        )}
        {state.kind === "ready" && state.rows.length > 0 && (
          <ul
            className="divide-y divide-border"
            data-testid="home-recent-list"
          >
            {state.rows.map((row) => (
              <li
                key={row.contract_id}
                className="flex items-center justify-between gap-3 py-2"
                data-testid="home-recent-row"
                data-contract-id={row.contract_id}
              >
                <button
                  type="button"
                  className="flex min-w-0 flex-1 flex-col items-start text-left transition-colors hover:bg-accent/40 focus:outline-none focus:ring-2 focus:ring-ring rounded-sm px-1 -mx-1"
                  onClick={() => onOpenContract(row.contract_id)}
                  data-testid="home-recent-row-button"
                >
                  <span className="truncate text-sm font-medium">
                    {row.filename}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {pipelineStageLabel(row)} ·{" "}
                    {formatRelativeTime(row.last_touched_at)}
                    {row.flag_count > 0 && (
                      <> · {row.flag_count} flag{row.flag_count === 1 ? "" : "s"}</>
                    )}
                  </span>
                </button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onOpenContract(row.contract_id)}
                  data-testid="home-recent-row-open"
                >
                  Open review
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}