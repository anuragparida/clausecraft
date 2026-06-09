// Phase 4 client-side language detector.
//
// Purpose
// -------
// The upload form's "Auto" picker option needs a *preview* of
// what language the uploaded file is in, so the user can see
// (and override) what the backend will eventually get as the
// ``language`` form field. The backend is still the source of
// truth for the per-clause language (see card t_4c21627c —
// DE clause taxonomy + per-clause language detection, which
// does the real parse-time detection). This client-side
// detector is best-effort, used only for the picker preview.
//
// Algorithm
// ---------
// A tiny stopword-frequency heuristic. The text is
// lower-cased, tokenised on Unicode letter runs, and each
// token is matched against two small hand-picked stopword
// sets (DE and EN). The language with the higher stopword
// density wins. Ties, empty input, and very short input
// (< 20 tokens) all fall back to "en" — the Phase 4 spec
// marks English as the historical default and the cost of a
// false "de" on a short EN text is much higher than the
// cost of a false "en" on a short DE text (the user can
// always override the picker).
//
// What it deliberately is NOT
// ----------------------------
// - Not langdetect / CLD. Adding a 30-MB language-detection
//   library for a 95%-case heuristic is not in scope.
// - Not a real parser. PDF / DOCX bytes are opaque to the
//   browser; this works on plain text or the first chunk of
//   an extracted document. The picker preview uses the
//   first ~2 KB of the file as text where possible; for
//   binary formats the detector returns "en" as a safe
//   default and the backend re-detects at parse time.

import type { SupportedLanguage } from "@/i18n";

// --- Stopword sets -----------------------------------------------------
//
// Hand-curated. Each entry is a *function word* (pronoun,
// preposition, article, common conjunction) that is highly
// frequent in legal / contract text and is unambiguous
// between DE and EN. No content words ("Vertrag" /
// "contract") — content words can be loanwords, and the
// heuristic should be robust to the EN NDA mentioning
// "Vertraulichkeitsvereinbarung" in passing.

/** German function words. Lower-case. ~25 entries. */
const DE_STOPWORDS: ReadonlySet<string> = new Set([
  // articles
  "der", "die", "das", "den", "dem", "des",
  // common prepositions
  "von", "mit", "aus", "bei", "nach", "seit", "über",
  // common conjunctions
  "und", "oder", "aber", "wenn", "weil", "sowie", "sowohl",
  // common pronouns / determiners
  "ein", "eine", "einer", "eines", "kein", "keine", "keiner",
  // modals / auxiliaries
  "ist", "sind", "wird", "werden", "kann", "können", "muss", "müssen", "soll", "sollen",
  // very common DE-only
  "nicht", "auch", "nur", "noch", "sehr", "hier", "diese", "dieser", "diesem",
]);

/** English function words. Lower-case. ~25 entries. */
const EN_STOPWORDS: ReadonlySet<string> = new Set([
  // articles
  "the", "a", "an",
  // common prepositions
  "of", "in", "to", "for", "with", "by", "on", "at", "from", "as", "into",
  // common conjunctions
  "and", "or", "but", "if", "because", "so", "nor", "yet",
  // common pronouns / determiners
  "this", "that", "these", "those", "any", "all", "each", "every",
  // modals / auxiliaries
  "is", "are", "was", "were", "be", "been", "can", "could", "shall", "should", "must", "will", "would", "may", "might",
  // very common EN-only
  "not", "no", "yes", "any", "such", "its", "their",
]);

// --- Tokeniser ---------------------------------------------------------

/** Lower-case + split on non-letter runs. Letters are
 *  Unicode-aware via the ``\\p{L}`` class, so ä / ö / ü / ß
 *  all stay attached to their word. */
function tokenise(text: string): string[] {
  return text
    .toLowerCase()
    .split(/[^\p{L}]+/u)
    .filter((tok) => tok.length > 0);
}

// --- Detector ----------------------------------------------------------

/**
 * Detect the language of a string using the stopword
 * heuristic. Returns "en" for empty / very short /
 * ambiguous input.
 *
 * Exported for unit testing — the picker component calls
 * the higher-level :func:`detectLanguageFromFile` below
 * with a ``File`` object.
 */
export function detectLanguage(text: string): SupportedLanguage {
  const tokens = tokenise(text);
  // < 20 tokens: not enough signal. Default to EN.
  if (tokens.length < 20) return "en";

  let deHits = 0;
  let enHits = 0;
  for (const tok of tokens) {
    if (DE_STOPWORDS.has(tok)) deHits++;
    if (EN_STOPWORDS.has(tok)) enHits++;
  }

  if (deHits === 0 && enHits === 0) return "en";
  if (deHits === enHits) return "en";
  return deHits > enHits ? "de" : "en";
}

// --- File-level detector ----------------------------------------------

/** Maximum number of bytes to read from a file for the
 *  preview. 2 KB is enough to cross the 20-token threshold
 *  on plain-text inputs and is small enough to be instant
 *  on any modern browser. */
const SNIFF_BYTES = 2048;

/**
 * Read the first ~2 KB of a file as UTF-8 and run the
 * detector over it. For binary formats (PDF, DOCX) the
 * decoded string is mostly garbled, so the detector will
 * return "en" by default. The backend re-detects at parse
 * time — this client-side sniff is purely a preview aid.
 *
 * Failures (file unreadable, FileReader unsupported) are
 * swallowed and "en" is returned. The picker will then
 * default to EN, which the user can override.
 */
export function detectLanguageFromFile(
  file: File,
): Promise<SupportedLanguage> {
  return new Promise((resolve) => {
    // Defensive: not all File-like objects in tests have
    // a real ``slice`` (e.g. a stubbed object). If we
    // can't slice the file, default to "en" and let the
    // backend handle it.
    if (typeof file?.slice !== "function") {
      resolve("en");
      return;
    }

    const slice = file.slice(0, Math.min(SNIFF_BYTES, file.size));
    // Older browsers don't have ``Blob.text()``. The
    // FileReader fallback covers them. jsdom (used in
    // tests) supports ``Blob.text()`` natively.
    if (typeof slice.text === "function") {
      slice
        .text()
        .then((text) => resolve(detectLanguage(text)))
        .catch(() => resolve("en"));
      return;
    }
    try {
      const reader = new FileReader();
      reader.onload = () => {
        const text =
          typeof reader.result === "string" ? reader.result : "";
        resolve(detectLanguage(text));
      };
      reader.onerror = () => resolve("en");
      reader.readAsText(slice);
    } catch {
      resolve("en");
    }
  });
}
