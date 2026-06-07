import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

// shadcn-style Badge. The variant names follow the same convention as
// the shadcn/ui registry (default, secondary, destructive, outline)
// plus a small set of "type" variants we use to colour-code clause
// types in the Triage DataTable. The type-to-colour mapping is
// stable and is the only place where the colour choice lives — every
// caller renders a Badge with `variant="type-definition"` etc. and
// the colour rule is consistent.

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-primary-foreground hover:bg-primary/80",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80",
        outline: "text-foreground",
        // Clause-type colour-coding. Kept in the same file as the
        // other variants so the colour choice is one place to look
        // for when the Triage page style gets revisited.
        "type-definition":
          "border-transparent bg-blue-500/15 text-blue-700 dark:text-blue-300",
        "type-term":
          "border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-300",
        "type-governing_law":
          "border-transparent bg-purple-500/15 text-purple-700 dark:text-purple-300",
        "type-return_of_materials":
          "border-transparent bg-cyan-500/15 text-cyan-700 dark:text-cyan-300",
        "type-injunctive_relief":
          "border-transparent bg-rose-500/15 text-rose-700 dark:text-rose-300",
        "type-residual_knowledge":
          "border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
        "type-non_solicit":
          "border-transparent bg-orange-500/15 text-orange-700 dark:text-orange-300",
        "type-non_compete":
          "border-transparent bg-orange-500/15 text-orange-700 dark:text-orange-300",
        "type-indemnity":
          "border-transparent bg-red-500/15 text-red-700 dark:text-red-300",
        "type-limitation_of_liability":
          "border-transparent bg-red-500/15 text-red-700 dark:text-red-300",
        "type-assignment":
          "border-transparent bg-indigo-500/15 text-indigo-700 dark:text-indigo-300",
        "type-entire_agreement":
          "border-transparent bg-slate-500/15 text-slate-700 dark:text-slate-300",
        "type-severability":
          "border-transparent bg-slate-500/15 text-slate-700 dark:text-slate-300",
        "type-notices":
          "border-transparent bg-teal-500/15 text-teal-700 dark:text-teal-300",
        "type-counterparts":
          "border-transparent bg-teal-500/15 text-teal-700 dark:text-teal-300",
        "type-unknown":
          "border-transparent bg-zinc-500/15 text-zinc-700 dark:text-zinc-300",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
