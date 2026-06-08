import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

// SeverityBadge — color-codes the spotter's 0..3 score per
// docs/06-ui-spec.md (0=green, 1=yellow, 2=orange, 3=red). The
// colour rules live in this file so the whole visual contract is
// one place to look. The component is intentionally pure: it
// renders a single inline-flex span with a small label, no
// behaviour. The DeviationReview page owns the "which score goes
// here" logic.
//
// Three things to know when editing this file:
//
// 1. The variant order matches the score order. The `cva` below
//    declares one variant per score (`sev-0` ... `sev-3`) and
//    relies on the consumer passing the right `variant`. We do
//    not auto-derive the variant from `score` to keep the
//    component single-purpose — DeviationReview does the mapping
//    in one place so we can audit it.
// 2. `data-severity` is a test hook so the DeviationReview tests
//    can assert on the visual mapping without reaching into
//    Tailwind classnames.
// 3. Out-of-range scores are clamped to 0 — a defensive default
//    for when a new spotter model emits something we don't
//    recognise. The contract is "a flag for every clause, no
//    matter what", and a malformed score should render *something*
//    rather than throw.

const severityBadgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        "sev-0":
          "border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
        "sev-1":
          "border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-300",
        "sev-2":
          "border-transparent bg-orange-500/15 text-orange-700 dark:text-orange-300",
        "sev-3": "border-transparent bg-red-500/15 text-red-700 dark:text-red-300",
      },
    },
    defaultVariants: {
      variant: "sev-0",
    },
  }
);

export type SeverityScore = 0 | 1 | 2 | 3;

export interface SeverityBadgeProps
  extends Omit<React.HTMLAttributes<HTMLSpanElement>, "children">,
    VariantProps<typeof severityBadgeVariants> {
  /** Spotter score in 0..3. Out-of-range values are clamped to 0. */
  score: number;
  /** Optional label override. Defaults to `S{score}`. */
  label?: string;
}

const VARIANT_FOR_SCORE = {
  0: "sev-0",
  1: "sev-1",
  2: "sev-2",
  3: "sev-3",
} as const;

function clampScore(score: number): SeverityScore {
  if (score === 0) return 0;
  if (score === 1) return 1;
  if (score === 2) return 2;
  if (score === 3) return 3;
  // Defensive default for malformed scores (LLM emitting
  // floats, future schema changes, etc). The contract is "a
  // flag for every clause, no matter what", and a malformed
  // score should render *something* rather than throw. The
  // spec says 0=green = "aligned / no deviation", which is
  // the safe default for an unknown severity.
  return 0;
}

export function SeverityBadge({
  score,
  label,
  className,
  variant,
  ...props
}: SeverityBadgeProps) {
  const clamped = clampScore(score);
  const resolvedVariant = variant ?? VARIANT_FOR_SCORE[clamped];
  const resolvedLabel = label ?? `S${clamped}`;
  return (
    <span
      data-severity={clamped}
      data-testid="severity-badge"
      className={cn(severityBadgeVariants({ variant: resolvedVariant }), className)}
      {...props}
    >
      {resolvedLabel}
    </span>
  );
}

export { severityBadgeVariants };
