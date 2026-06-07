import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { DisclaimerFooter } from "@/components/DisclaimerFooter";
import { TriagePage } from "@/components/TriagePage";

// The Phase 0 / Phase 1 home view. Shows the project name, a
// "Triage contracts" entry point (the Phase 1 page), and a short
// status panel. Wired with a backend healthz check via the API proxy
// to prove the API ↔ UI connection works end-to-end.
//
// In Phase 1 the "Coming soon" panel is replaced by a "Triage
// contracts" link that navigates to the real /triage page. The
// Triage page is loaded via simple in-component state (no router)
// to keep the dependency surface minimal — react-router-dom is not
// needed yet.

type View = "home" | "triage";

function App() {
  const [view, setView] = useState<View>("home");

  if (view === "triage") {
    return <TriagePage />;
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
                typed clause list in a stable JSON schema. The deviation
                spotter and playbook land in Phase 2.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Upload a PDF or DOCX NDA, see the typed clause list with
                position, type, and a text excerpt. Classifier runs in
                rule-based fallback mode (no LLM key required) until
                Phase 2.
              </p>
              <Button
                onClick={() => setView("triage")}
                data-testid="home-triage-link"
              >
                Triage contracts
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
