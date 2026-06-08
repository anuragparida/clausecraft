import { useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// CitationPopover — click-to-reveal panel that shows the
// playbook baseline a flag cited, plus the exact contract
// excerpt that triggered the flag. Renders inline (no portal,
// no Radix) because Phase 2 wants a small component surface:
// 1 prop, 1 button, 1 panel. Phase 3 will swap this for a real
// shadcn Popover when the audit log lands.
//
// Behaviour:
// - `citation=null` or `unverified=true` → show "(no citation)"
//   placeholder text. We never throw on a missing citation; the
//   spotter contract is "a flag for every clause, no matter what",
//   so a missing citation is a *visual* state, not an error.
// - Otherwise show: `playbook_clause_id` (mono), the contract
//   excerpt (mono, truncated at ~200 chars with ellipsis), and
//   the source URL (clickable, opens in a new tab).
// - The trigger button label reflects the citation state:
//   "View citation" / "View citation (unverified)" / "No citation".
// - Toggleable; clicking the button or the close X closes it.
//
// Test hooks:
// - data-testid="citation-popover-trigger" / "-panel" / "-placeholder"
// - data-citation-state="cited" | "unverified" | "missing"

export interface Citation {
  playbook_clause_id: string;
  contract_text_excerpt: string;
  // Phase 2 renders the source URL when present; Phase 3 wires
  // this to the playbook viewer's deep link. Optional because
  // the API model has it as a separate field on the baseline
  // (not always carried in the SpotFlag payload).
  source_url?: string;
}

export interface CitationPopoverProps {
  citation: Citation | null | undefined;
  unverified?: boolean;
  /** Optional className for the trigger button wrapper. */
  className?: string;
}

const MAX_EXCERPT = 200;

function truncateExcerpt(text: string, max = MAX_EXCERPT): string {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (cleaned.length <= max) return cleaned;
  return cleaned.slice(0, max - 1) + "…";
}

type CitationState = "cited" | "unverified" | "missing";

function resolveState(
  citation: Citation | null | undefined,
  unverified: boolean
): CitationState {
  if (!citation) return "missing";
  if (unverified) return "unverified";
  return "cited";
}

export function CitationPopover({
  citation,
  unverified = false,
  className,
}: CitationPopoverProps) {
  const [open, setOpen] = useState(false);
  const state = resolveState(citation, unverified);
  const hasContent = state !== "missing";

  const triggerLabel =
    state === "missing"
      ? "No citation"
      : state === "unverified"
        ? "View citation (unverified)"
        : "View citation";

  return (
    <div className={cn("inline-flex flex-col items-start gap-1", className)}>
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={() => hasContent && setOpen((o) => !o)}
        disabled={!hasContent}
        data-testid="citation-popover-trigger"
        data-citation-state={state}
        aria-expanded={open}
      >
        {triggerLabel}
      </Button>
      {open && hasContent && citation && (
        <div
          role="dialog"
          aria-label="Citation details"
          data-testid="citation-popover-panel"
          data-citation-state={state}
          className="mt-1 w-80 max-w-full rounded-md border bg-card p-3 text-xs shadow-sm"
        >
          <div className="mb-2 flex items-start justify-between gap-2">
            <div className="font-semibold uppercase tracking-wide text-muted-foreground">
              Citation
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="text-muted-foreground hover:text-foreground"
              aria-label="Close citation"
              data-testid="citation-popover-close"
            >
              ×
            </button>
          </div>
          <dl className="space-y-2">
            <div>
              <dt className="text-muted-foreground">Playbook clause</dt>
              <dd
                className="font-mono text-foreground"
                data-testid="citation-playbook-id"
              >
                {citation.playbook_clause_id}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Contract excerpt</dt>
              <dd
                className="font-mono text-foreground"
                data-testid="citation-excerpt"
              >
                {truncateExcerpt(citation.contract_text_excerpt)}
              </dd>
            </div>
            {citation.source_url && (
              <div>
                <dt className="text-muted-foreground">Source</dt>
                <dd>
                  <a
                    className="text-primary underline"
                    href={citation.source_url}
                    target="_blank"
                    rel="noreferrer noopener"
                    data-testid="citation-source-url"
                  >
                    {citation.source_url}
                  </a>
                </dd>
              </div>
            )}
          </dl>
        </div>
      )}
    </div>
  );
}

export { truncateExcerpt };
