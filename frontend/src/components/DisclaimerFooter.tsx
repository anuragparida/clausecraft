import { DISCLAIMER_PARAGRAPHS, DISCLAIMER_TAGLINE } from "@/lib/disclaimer";

// Footer is present on every page. In Phase 0 there's only one page,
// but the component is extracted so the layout stays clean as the
// app grows.
//
// Renders the canonical DISCLAIMER.md text in full. The short
// 4-word tagline ("Not legal advice.") is kept as a banner above
// the paragraphs (spec line 287 — "Not legal advice" banner rule).

export function DisclaimerFooter() {
  return (
    <footer className="border-t border-border bg-background">
      <div className="mx-auto max-w-5xl px-6 py-4 text-xs text-muted-foreground space-y-2">
        <p className="font-semibold text-foreground">{DISCLAIMER_TAGLINE}</p>
        {DISCLAIMER_PARAGRAPHS.map((para, i) => (
          <p key={i}>{para}</p>
        ))}
      </div>
    </footer>
  );
}
