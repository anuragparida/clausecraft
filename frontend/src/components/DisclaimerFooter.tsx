import { DISCLAIMER_TEXT } from "@/lib/disclaimer";

// Footer is present on every page. In Phase 0 there's only one page,
// but the component is extracted so the layout stays clean as the
// app grows.

export function DisclaimerFooter() {
  return (
    <footer className="border-t border-border bg-background">
      <div className="mx-auto max-w-5xl px-6 py-4 text-xs text-muted-foreground">
        {DISCLAIMER_TEXT}
      </div>
    </footer>
  );
}
