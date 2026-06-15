// Phase 5 — counterparty type picker (t_1e6fa8e2).
//
// Scope (per card body)
// ---------------------
// Single component, no refactor of the upload form. Four
// radio options, one per axis in the spec's counterparty
// matrix:
//
//   - enterprise  (commercial, default — most common)
//   - smb         (small / medium business)
//   - public_sector (government / procurement / FOIA-style)
//   - healthcare  (HIPAA / BSI / sector-specific data protection)
//
// Plus a 5th "any" sentinel for callers that don't want to
// pick a type (the Phase 2 default). The card body lists
// the 4 axes as the spec's counterparty types; the
// 5th "any" option is the Phase 2 back-compat fallback the
// spec mentions ("…or the legacy 'any' sentinel").
//
// What this component does
// ------------------------
//   - Renders a labeled radio group: enterprise / SMB /
//     public-sector / healthcare / any.
//   - Surfaces the picked value via ``onChange``; the
//     parent (TriagePage) forwards it as a ``counterparty_type``
//     form field on the ingest POST so the spot stage can
//     consult the right matrix cell.
//   - Reads its label from the i18n shim (``pick.*``) so
//     the picker flips language with the rest of the page
//     chrome. Phase 4 ships the English labels in JSX; the
//     DE labels come from ``de.json`` (Athena's card).
//
// What this component does NOT do
// -------------------------------
//   - Submit the form. The parent owns the form / mutation /
//     network call.
//   - Persist the choice across uploads. The picker state
//     resets when the parent mounts a new instance.
//   - Validate the picked value. The 4 axes are the spec's
//     canonical list and the radio buttons only let the
//     user pick from the list — there's nothing to
//     validate. The backend normalises unknown values to
//     ``"any"`` (v1 plumbing) and logs a warning.

import { useId } from "react";
import type { SupportedLanguage } from "@/i18n";
import { t as _t } from "@/i18n";

// --- Types -------------------------------------------------------------

/**
 * The 4 Phase 5 counterparty axes + the legacy ``"any"``
 * sentinel. The 4 axes are the spec's canonical list; the
 * sentinel is the Phase 2 back-compat default. Backend code
 * (e.g. ``app.agents.deviation_spotter.schema`` and
 * ``app.playbook.counterparty``) treats both forms as valid
 * inputs.
 */
export type CounterpartyType =
  | "enterprise"
  | "smb"
  | "public_sector"
  | "healthcare"
  | "any";

export interface CounterpartyPickerProps {
  /** The currently picked value. */
  value: CounterpartyType;
  /** Called when the user picks a different value. */
  onChange: (value: CounterpartyType) => void;
  /** The language to render the picker's own labels in.
   *  Defaults to "en" (the JSX-native labels). */
  displayLanguage?: SupportedLanguage;
  /** Disable all radios. */
  disabled?: boolean;
}

// --- Component ---------------------------------------------------------

/**
 * Human-readable label per counterparty type, used in the
 * popover's lookup-chain tooltip and the picker's own
 * labels. Kept here (not in the i18n JSON) because the
 * values are *identifiers* — the same word appears in the
 * backend, the matrix YAML, and the audit trail. The
 * picker's i18n layer wraps these with a "Counterparty type"
 * label and a "Showing" prefix.
 */
export function counterpartyTypeLabel(t: CounterpartyType): string {
  switch (t) {
    case "enterprise":
      return "Enterprise";
    case "smb":
      return "SMB";
    case "public_sector":
      return "Public sector";
    case "healthcare":
      return "Healthcare";
    case "any":
      return "Any (Phase 2 default)";
  }
}

/** Resolve a label via the i18n shim. Phase 4 has DE
 *  translations for the picker labels; the EN labels are
 *  the JSX fallbacks (the shim returns the key for ``en``,
 *  which we then map to the human label below). */
function pickerLabel(key: string, displayLanguage: SupportedLanguage): string {
  // Same pattern as LanguagePicker: ship a small EN
  // fallback table, and let the shim look up DE
  // equivalents under ``counterparty_picker.*`` keys.
  const EN_FALLBACK: Record<string, string> = {
    "counterparty_picker.label": "Counterparty type",
    "counterparty_picker.option.enterprise": "Enterprise",
    "counterparty_picker.option.smb": "SMB",
    "counterparty_picker.option.public_sector": "Public sector",
    "counterparty_picker.option.healthcare": "Healthcare",
    "counterparty_picker.option.any": "Any (Phase 2 default)",
    "counterparty_picker.help": (
      "The matrix's 4-axis column. The spot stage consults " +
      "the (clause_type, counterparty_type) cell."
    ),
  };
  const resolved = _t(key, displayLanguage);
  // If the shim returned the key (no translation found),
  // fall back to the EN string table above.
  if (resolved === key) return EN_FALLBACK[key] ?? key;
  return resolved;
}

const OPTIONS: Array<{
  value: CounterpartyType;
  labelKey: string;
  /** Short hint shown under the label (always EN; UX
   *  microcopy, not localisable). */
  hint: string;
}> = [
  {
    value: "enterprise",
    labelKey: "counterparty_picker.option.enterprise",
    hint: "commercial",
  },
  {
    value: "smb",
    labelKey: "counterparty_picker.option.smb",
    hint: "small / medium business",
  },
  {
    value: "public_sector",
    labelKey: "counterparty_picker.option.public_sector",
    hint: "government / procurement",
  },
  {
    value: "healthcare",
    labelKey: "counterparty_picker.option.healthcare",
    hint: "HIPAA / BSI / sector-specific",
  },
  {
    value: "any",
    labelKey: "counterparty_picker.option.any",
    hint: "Phase 2 flat baseline",
  },
];

export function CounterpartyPicker({
  value,
  onChange,
  displayLanguage = "en",
  disabled = false,
}: CounterpartyPickerProps) {
  const groupId = useId();

  return (
    <div
      className="flex flex-col gap-2"
      data-testid="counterparty-picker"
      data-value={value}
    >
      <label
        className="text-sm font-medium leading-none"
        id={`${groupId}-label`}
      >
        {pickerLabel("counterparty_picker.label", displayLanguage)}
      </label>
      <div
        role="radiogroup"
        aria-labelledby={`${groupId}-label`}
        className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:gap-3"
        data-testid="counterparty-picker-group"
      >
        {OPTIONS.map((opt) => {
          const isChecked = value === opt.value;
          return (
            <label
              key={opt.value}
              className={
                "inline-flex flex-col gap-0.5 rounded-md border px-3 py-2 text-sm transition-colors " +
                (disabled
                  ? "cursor-not-allowed opacity-50"
                  : "cursor-pointer hover:bg-muted/40") +
                (isChecked
                  ? " border-primary bg-primary/5"
                  : " border-muted-foreground/25 bg-muted/20")
              }
              data-testid={`counterparty-picker-option-${opt.value}`}
              data-checked={isChecked ? "true" : "false"}
            >
              <span className="inline-flex items-center gap-2">
                <input
                  type="radio"
                  name={`${groupId}-counterparty`}
                  value={opt.value}
                  checked={isChecked}
                  disabled={disabled}
                  onChange={() => onChange(opt.value)}
                  className="h-3.5 w-3.5 accent-primary"
                  data-testid={`counterparty-picker-input-${opt.value}`}
                />
                <span className="font-medium">
                  {pickerLabel(opt.labelKey, displayLanguage)}
                </span>
              </span>
              <span className="ml-5 text-[11px] text-muted-foreground">
                {opt.hint}
              </span>
            </label>
          );
        })}
      </div>
      <p
        className="text-xs text-muted-foreground"
        data-testid="counterparty-picker-help"
      >
        {pickerLabel("counterparty_picker.help", displayLanguage)}
      </p>
    </div>
  );
}

export default CounterpartyPicker;
