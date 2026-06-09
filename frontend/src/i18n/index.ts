// Phase 4 minimal i18n shim.
//
// The picker card (t_b4eb39a6) ships this consumer. The DE
// strings themselves are produced by Athena's card
// (t_5cf4cb97) and live in `de.json`. The shim is intentionally
// tiny:
//
//   - Two languages only: "en" and "de". Phase 5 may add more
//     (French for an EU DPA demo?); this card explicitly does
//     not generalise beyond two.
//   - Lookup is a flat dotted path ("triage.title") into a
//     nested object. The JSON files are kept flat / one level
//     of nesting max — see `de.json` `_meta._comment` for the
//     rationale.
//   - "en" never reads from a JSON file. The Phase 1 / 2 / 3
//     codebase has English copy hard-coded in JSX. Switching a
//     page to "en" therefore means "render the existing
//     English text" — and the lookup just returns the dotted
//     key as the fallback (so missing keys are visible, not
//     silently translated).
//   - "de" reads from `de.json`. If a key is missing, the shim
//     falls back to the dotted key — same "visible, not
//     silent" rule. This matches the Phase 4 scope rule that
//     the JSON is the source of truth for the DE strings and
//     the picker is just the consumer; if a translation is
//     missing we want the gap to show up at runtime, not be
//     papered over with an English string.
//
// Out of scope (per card body):
//   - Pluralisation, gendering, ICU message format.
//   - Lazy-loading or per-route bundles. The JSON is ~12 KB
//     and is shipped with the bundle; Phase 4 does not need
//     code-splitting.
//   - Right-to-left or RTL handling. German is LTR.

import deJson from "./de.json";

// --- Types --------------------------------------------------------------

export type SupportedLanguage = "en" | "de";

/** The shape of a single locale bundle. */
type LocaleBundle = Record<string, unknown>;

/** Cast the imported JSON to a plain bundle. The JSON file's
 *  structure is hand-maintained and kept flat-ish (a few
 *  region keys per page); this type just enforces that. */
const deBundle = deJson as unknown as LocaleBundle;

/** All available bundles, keyed by language code. */
const bundles: Record<SupportedLanguage, LocaleBundle | null> = {
  en: null, // English is JSX-resident; no bundle needed.
  de: deBundle,
};

// --- Lookup -------------------------------------------------------------

/**
 * Walk a dotted path into a nested object and return the
 * leaf value as a string. Returns ``undefined`` if any
 * segment is missing.
 *
 * Examples:
 *   - getByPath({a: {b: "x"}}, "a.b") → "x"
 *   - getByPath({a: {b: "x"}}, "a.c") → undefined
 *   - getByPath({a: "x"}, "a.b")      → undefined
 *     (cannot traverse into a string)
 */
function getByPath(bundle: LocaleBundle, path: string): string | undefined {
  const segments = path.split(".");
  let current: unknown = bundle;
  for (const seg of segments) {
    if (current === null || typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[seg];
  }
  return typeof current === "string" ? current : undefined;
}

// --- Public API ---------------------------------------------------------

/**
 * Translate a dotted key in the active language.
 *
 * Resolution order:
 *   1. The active language's bundle (e.g. ``de.json``).
 *   2. The dotted key itself (visible, non-silent fallback).
 *
 * Note that "en" deliberately has no bundle — the caller's
 * JSX still uses its hard-coded English copy. The lookup
 * is invoked at runtime only when the caller wants to render
 * a DE string; for EN pages the lookup is never called.
 */
export function t(key: string, language: SupportedLanguage): string {
  if (language === "en") {
    // No bundle. Returning the key is a deliberate no-op
    // for EN — the JSX is responsible for its own copy.
    return key;
  }
  const bundle = bundles[language];
  if (!bundle) return key;
  const value = getByPath(bundle, key);
  return value ?? key;
}

/**
 * Pick the language to render for a given user-picked
 * (or auto-detected) language. This is a one-liner today
 * but exists as a hook for the future "fall back to EN if
 * DE strings are missing" rule. Phase 4 keeps it trivial.
 */
export function resolveLanguage(
  picked: SupportedLanguage | "auto",
  detected: SupportedLanguage,
): SupportedLanguage {
  return picked === "auto" ? detected : picked;
}
