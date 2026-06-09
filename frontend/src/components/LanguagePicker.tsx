// Phase 4 — DE UI language picker.
//
// Scope (per card t_b4eb39a6 body)
// --------------------------------
// Single component, no refactor of the upload form. Three
// choices: "auto" (best-effort client-side detect), "en",
// "de". The picked value is reported to the parent via
// :prop:`onChange`; the parent (TriagePage) is responsible
// for the form field, the chrome string swap, and the rest
// of the wiring.
//
// What this component does
// ------------------------
//   - Renders a labeled radio group: "Auto" / "English" /
//     "Deutsch".
//   - Surfaces a small "Detected: Deutsch" hint when the
//     active mode is "auto" and a detect result is
//     available, so the user can see the heuristic in
//     action before they trust it.
//   - Reads its label from the i18n shim (``pick.*``) so
//     the picker itself flips language with the rest of
//     the page chrome. Phase 4 ships the English labels in
//     JSX; the DE labels come from ``de.json``. If a
//     translation is missing, the shim returns the key —
//     visible, not silent.
//
// What this component does NOT do
// -------------------------------
//   - Read the file. The parent decides when to call
//     :func:`detectLanguageFromFile` (typically on file
//     select). The picker just renders the result.
//   - Submit the form. The parent owns the form /
//     mutation / network call.
//   - Persist the choice across uploads. The picker state
//     resets when the parent mounts a new instance.

import { useId } from "react";
import type { SupportedLanguage } from "@/i18n";
import { t as _t } from "@/i18n";

// --- Types -------------------------------------------------------------

export type PickerValue = SupportedLanguage | "auto";

export interface LanguagePickerProps {
  /** The currently picked value. */
  value: PickerValue;
  /** Called when the user picks a different value. */
  onChange: (value: PickerValue) => void;
  /** The language to render the picker's own labels in.
   *  Defaults to "en" (the JSX-native labels). */
  displayLanguage?: SupportedLanguage;
  /** The detector's best guess, used to render the
   *  "Detected: …" hint when ``value === "auto"``.
   *  Optional — when absent, the hint is hidden. */
  detected?: SupportedLanguage;
  /** Disable all three radios. */
  disabled?: boolean;
}

// --- Component ---------------------------------------------------------

/** Human-readable label per language, for the "Detected: …"
 *  hint. Kept here (not in the i18n JSON) because it's
 *  a status string, not user-facing copy that needs the
 *  legal register. */
function languageDisplayName(lang: SupportedLanguage): string {
  if (lang === "de") return "Deutsch";
  return "English";
}

/** Resolve a label via the i18n shim. Phase 4 has DE
 *  translations for the picker labels; the EN labels are
 *  the JSX fallbacks (the shim returns the key for ``en``,
 *  which we then map to the human label below). */
function pickerLabel(key: string, displayLanguage: SupportedLanguage): string {
  // The de.json has ``common.choose_file`` etc., but the
  // picker's own labels are not page chrome — they are the
  // picker chrome. So we ship small, EN-fallback strings
  // and let the shim look up DE equivalents under
  // ``picker.*`` keys.
  const EN_FALLBACK: Record<string, string> = {
    "picker.label": "Contract language",
    "picker.option.auto": "Auto",
    "picker.option.en": "English",
    "picker.option.de": "Deutsch",
    "picker.detected_prefix": "Detected:",
    "picker.detected_hint": "(preview — backend re-detects at parse time)",
  };
  const resolved = _t(key, displayLanguage);
  // If the shim returned the key (no translation found),
  // fall back to the EN string table above.
  if (resolved === key) return EN_FALLBACK[key] ?? key;
  return resolved;
}

export function LanguagePicker({
  value,
  onChange,
  displayLanguage = "en",
  detected,
  disabled = false,
}: LanguagePickerProps) {
  const groupId = useId();

  const options: Array<{ value: PickerValue; labelKey: string }> = [
    { value: "auto", labelKey: "picker.option.auto" },
    { value: "en", labelKey: "picker.option.en" },
    { value: "de", labelKey: "picker.option.de" },
  ];

  return (
    <div
      className="flex flex-col gap-2"
      data-testid="language-picker"
      data-value={value}
    >
      <label
        className="text-sm font-medium leading-none"
        id={`${groupId}-label`}
      >
        {pickerLabel("picker.label", displayLanguage)}
      </label>
      <div
        role="radiogroup"
        aria-labelledby={`${groupId}-label`}
        className="flex flex-wrap gap-3"
      >
        {options.map((opt) => {
          const isChecked = value === opt.value;
          return (
            <label
              key={opt.value}
              className={
                "inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm transition-colors " +
                (disabled
                  ? "cursor-not-allowed opacity-50"
                  : "cursor-pointer hover:bg-muted/40") +
                (isChecked
                  ? " border-primary bg-primary/5"
                  : " border-muted-foreground/25 bg-muted/20")
              }
              data-testid={`language-picker-option-${opt.value}`}
              data-checked={isChecked ? "true" : "false"}
            >
              <input
                type="radio"
                name={`${groupId}-language`}
                value={opt.value}
                checked={isChecked}
                disabled={disabled}
                onChange={() => onChange(opt.value)}
                className="h-3.5 w-3.5 accent-primary"
                data-testid={`language-picker-input-${opt.value}`}
              />
              <span>{pickerLabel(opt.labelKey, displayLanguage)}</span>
            </label>
          );
        })}
      </div>
      {value === "auto" && detected && (
        <p
          className="text-xs text-muted-foreground"
          data-testid="language-picker-detected"
          data-detected={detected}
        >
          {pickerLabel("picker.detected_prefix", displayLanguage)}{" "}
          <span className="font-mono">{languageDisplayName(detected)}</span>{" "}
          {pickerLabel("picker.detected_hint", displayLanguage)}
        </p>
      )}
    </div>
  );
}

export default LanguagePicker;
