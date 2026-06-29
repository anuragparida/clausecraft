import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { DisclaimerFooter } from "@/components/DisclaimerFooter";
import { RecentContractsCard } from "@/components/RecentContractsCard";
import { TriagePage } from "@/components/TriagePage";
import {
  DeviationReviewPage,
  SAMPLE_DEVIATION_REVIEW_DATA,
} from "@/pages/DeviationReview";
import { AuditReplayPage } from "@/pages/AuditReplay";
import { RedlineOutputPage } from "@/pages/RedlineOutput";
import { ReviewContractPage } from "@/pages/ReviewContract";
import { matchPath, useHashRoute } from "@/lib/router";

// clausecraft — Phase 0/1/2/3 entry shell.
//
// Routing
// -------
// Phase 0/1/2: useState-driven view switch. The home view
// renders the three nav cards. Each card sets the view.
//
// Phase 3: hash-routed URLs. The Phase 3 spec mandates
// stable, refresh-safe URLs for the review / audit /
// redline pages. The hash router (``lib/router.ts``)
// handles the parse; the route table below does the
// dispatch. The Phase 0/1/2 view strings ("triage",
// "deviation") still work — they're the standalone home
// paths, equivalent to the old behaviour for the demo
// user clicking from the home page.
//
// Why hash routing
// ----------------
// Vite's dev server has no history fallback. Hash routes
// (e.g. ``#/contracts/abc/review``) survive a page refresh
// without any server config. Production deploy will swap
// in a real router (Phase 5) — the routes here are
// forward-compatible.
//
// Route table
// -----------
//   /                                  → home
//   /triage                            → Triage (upload)
//   /review                            → standalone deviation review
//   /contracts/:id/review              → connected review (Phase 3)
//   /contracts/:id/audit               → audit replay (Phase 3)
//   /contracts/:id/redline             → redline output (Phase 3)

// --- Bridge: hash routes → React views --------------------------------

function RouteOutlet() {
  const route = useHashRoute();

  // /contracts/:id/review
  const reviewMatch = matchPath("/contracts/:id/review", route.path);
  if (reviewMatch) {
    return (
      <ReviewContractPage
        contractId={reviewMatch.id}
        onBackToHome={() => (window.location.hash = "#/")}
        onViewAudit={() =>
          (window.location.hash = `#/contracts/${reviewMatch.id}/audit`)
        }
        onRedlineReady={() =>
          (window.location.hash = `#/contracts/${reviewMatch.id}/redline`)
        }
      />
    );
  }

  // /contracts/:id/audit
  const auditMatch = matchPath("/contracts/:id/audit", route.path);
  if (auditMatch) {
    return (
      <AuditReplayPage
        contractId={auditMatch.id}
        onBackToHome={() => (window.location.hash = "#/")}
        onBackToReview={() =>
          (window.location.hash = `#/contracts/${auditMatch.id}/review`)
        }
      />
    );
  }

  // /contracts/:id/redline
  const redlineMatch = matchPath("/contracts/:id/redline", route.path);
  if (redlineMatch) {
    return (
      <RedlineOutputPage
        contractId={redlineMatch.id}
        onBackToHome={() => (window.location.hash = "#/")}
        onBackToReview={() =>
          (window.location.hash = `#/contracts/${redlineMatch.id}/review`)
        }
        onViewAudit={() =>
          (window.location.hash = `#/contracts/${redlineMatch.id}/audit`)
        }
      />
    );
  }

  // /triage
  if (route.path === "/triage") {
    return <TriagePage />;
  }

  // /review — the standalone home-view demo (no contract id)
  if (route.path === "/review") {
    return (
      <DeviationReviewPage
        data={SAMPLE_DEVIATION_REVIEW_DATA}
        onBackToHome={() => (window.location.hash = "#/")}
        onBackToTriage={() => (window.location.hash = "#/triage")}
      />
    );
  }

  // Default: home
  return <HomeView onNavigate={(to) => (window.location.hash = `#${to}`)} />;
}

// --- Home view ---------------------------------------------------------

function HomeView({ onNavigate }: { onNavigate: (to: string) => void }) {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <main className="flex-1">
        <div className="mx-auto flex max-w-5xl flex-col gap-8 px-6 py-16">
          <header className="space-y-2">
            <h1 className="text-4xl font-bold tracking-tight">clausecraft</h1>
            <p className="text-muted-foreground">
              Upload a contract, get a deviation table against a public-source
              playbook, approve the redlines you want, download a tracked-changes
              .docx. Every flag is cited. Nothing is trusted by default.
            </p>
          </header>

          <Card className="max-w-2xl">
            <CardHeader>
              <CardTitle>Triage contracts</CardTitle>
              <CardDescription>
                Phase 1 — ingest, parse, and classify an NDA. Returns a
                typed clause list in a stable JSON schema.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Upload a PDF or DOCX NDA, see the typed clause list with
                position, type, and a text excerpt.
              </p>
              <Button
                onClick={() => onNavigate("/triage")}
                data-testid="home-triage-link"
              >
                Triage contracts
              </Button>
            </CardContent>
          </Card>

          <Card className="max-w-2xl">
            <CardHeader>
              <CardTitle>Deviation review (demo)</CardTitle>
              <CardDescription>
                Phase 2 — the main work surface. Color-coded flags with
                citations, per-row Approve / Reject / Edit / Add-context
                actions. Wired to local state; the connected review page
                (Phase 3) routes through the API.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Loads sample deviation flags (2 rows: one cited
                material deviation, one no-baseline) so the page is
                reachable without the backend.
              </p>
              <Button
                onClick={() => onNavigate("/review")}
                data-testid="home-deviation-link"
              >
                Open Deviation review
              </Button>
            </CardContent>
          </Card>

          <Card className="max-w-2xl">
            <CardHeader>
              <CardTitle>Phase 3 routes</CardTitle>
              <CardDescription>
                The two-view UI: live review (with real audit-log wiring)
                and audit replay (a read-only timeline of every decision).
                Open one of the demo routes below — the contract id
                ``demo-001`` is a stand-in for whatever id the upload
                flow would return.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Both routes hit the Phase 3 API. With Build 3 not yet
                fully landed, the data will be empty — that's a
                feature, not a bug: the route is wired, the page
                renders, the audit log endpoint gets called.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  onClick={() => onNavigate("/contracts/demo-001/review")}
                  data-testid="home-review-link"
                >
                  Open connected review
                </Button>
                <Button
                  variant="outline"
                  onClick={() => onNavigate("/contracts/demo-001/audit")}
                  data-testid="home-audit-link"
                >
                  Open audit replay
                </Button>
                <Button
                  variant="outline"
                  onClick={() => onNavigate("/contracts/demo-001/redline")}
                  data-testid="home-redline-link"
                >
                  Open redline output
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Phase 6 — Recent contracts card.

              Fills the first of the three reserved home-grid
              slots. The slot pattern (three siblings reserve
              the layout for unmerged sibling cards) was set
              up by the home-grid refactor; sibling cards
              (Leaderboard, Pipeline Status) own the other two
              slots. When this card grows (e.g. a "see all"
              link), the slot can be promoted to a wider
              column with `md:col-span-2`. */}
          <RecentContractsCard
            onOpenContract={(id) =>
              onNavigate(`/contracts/${encodeURIComponent(id)}/review`)
            }
          />
        </div>
      </main>
      <DisclaimerFooter />
    </div>
  );
}

// --- App ---------------------------------------------------------------

function App() {
  // Single entry point. All routing is handled inside
  // ``RouteOutlet`` via the hash router. The App component
  // itself stays minimal so it has nothing of its own to
  // test — every page is mounted directly by the test
  // suite.
  return <RouteOutlet />;
}

export default App;
