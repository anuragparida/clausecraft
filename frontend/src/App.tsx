import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { DisclaimerFooter } from "@/components/DisclaimerFooter";
import { TriagePage } from "@/components/TriagePage";
import {
  DeviationReviewPage,
  SAMPLE_DEVIATION_REVIEW_DATA,
} from "@/pages/DeviationReview";

// The Phase 0 / Phase 1 home view. Shows the project name, the
// navigation entry points to the real pages (Triage in Phase 1,
// Deviation Review in Phase 2), and a short status panel.
//
// Navigation is plain `useState` — no react-router-dom. The
// view string is the source of truth; switch on it. Phase 3 may
// swap to a real router if the page count grows.

type View = "home" | "triage" | "deviation";

function App() {
  const [view, setView] = useState<View>("home");

  if (view === "triage") {
    return <TriagePage />;
  }
  if (view === "deviation") {
    return (
      <DeviationReviewPage
        data={SAMPLE_DEVIATION_REVIEW_DATA}
        onBackToHome={() => setView("home")}
        onBackToTriage={() => setView("triage")}
      />
    );
  }

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
                onClick={() => setView("triage")}
                data-testid="home-triage-link"
              >
                Triage contracts
              </Button>
            </CardContent>
          </Card>

          <Card className="max-w-2xl">
            <CardHeader>
              <CardTitle>Deviation review</CardTitle>
              <CardDescription>
                Phase 2 — the main work surface. Color-coded flags with
                citations, per-row Approve / Reject / Edit actions.
                Buttons are wired to local state only; persistence
                arrives in Phase 3.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Loads sample deviation flags (2 rows: one cited
                material deviation, one no-baseline) so the page is
                reachable without the backend. Phase 3 wires this to
                the live spot endpoint.
              </p>
              <Button
                onClick={() => setView("deviation")}
                data-testid="home-deviation-link"
              >
                Open Deviation review
              </Button>
            </CardContent>
          </Card>
        </div>
      </main>
      <DisclaimerFooter />
    </div>
  );
}

export default App;
