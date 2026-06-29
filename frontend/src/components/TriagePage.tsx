import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { DisclaimerFooter } from "@/components/DisclaimerFooter";
import { LanguagePicker, type PickerValue } from "@/components/LanguagePicker";
import { detectLanguageFromFile } from "@/lib/detectLanguage";
import { resolveLanguage, t as i18nT, type SupportedLanguage } from "@/i18n";

// --- API types ----------------------------------------------------------

// Shape returned by ``POST /contracts/ingest``. Mirrors the FastAPI
// ``IngestResponse`` model 1:1. The backend is the source of truth
// for the field names; if the backend adds a field, we add it here.
export interface IngestResponseClause {
  id: string;
  text: string;
  position: {
    section: string;
    section_title: string;
    paragraph_index: number[];
  };
  type: string;
  language: string;
  confidence: number;
}

export interface IngestResponse {
  filename: string;
  format: string;
  clause_count: number;
  classified_count: number;
  classified_ratio: number;
  char_count: number;
  is_scanned: boolean;
  scanned_warning: string;
  clauses: IngestResponseClause[];
}

// --- Helpers ------------------------------------------------------------

const API_BASE = "/api";

// Trim a long clause text to ``max`` chars + an ellipsis. Used for
// the DataTable's "excerpt" column so the row stays scannable.
function truncate(text: string, max = 90): string {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (cleaned.length <= max) return cleaned;
  return cleaned.slice(0, max - 1) + "…";
}

// Map a backend ``ClauseType`` to a Badge variant. Mirrors the keys
// declared in ``components/ui/badge.tsx`` — keep them in sync.
function badgeVariantForType(type: string): string {
  if (type === "unknown") return "type-unknown";
  return `type-${type}`;
}

// --- Dropzone -----------------------------------------------------------

interface DropzoneProps {
  onFile: (file: File) => void;
  disabled: boolean;
  /** Picker's display language — only the dropzone hint text
   *  is localised (button labels, etc., are JSX). */
  displayLanguage: SupportedLanguage;
}

function Dropzone({ onFile, disabled, displayLanguage }: DropzoneProps) {
  const [dragOver, setDragOver] = useState(false);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragOver(false);
      if (disabled) return;
      const file = e.dataTransfer.files?.[0];
      if (file) onFile(file);
    },
    [onFile, disabled]
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) onFile(file);
      // Allow re-uploading the same file by clearing the input.
      e.target.value = "";
    },
    [onFile]
  );

  // The dropzone hint: a few hard-coded EN words, plus a small
  // DE string from the i18n shim when displayLanguage === "de".
  // The full i18n coverage of this page is out of scope for
  // Phase 4 (per card t_b4eb39a6 body — "minimal i18n shim
  // that reads DE strings from a JSON file"; the JSON ships
  // by Athena's card). The picker is the primary deliverable.
  const dropzoneHint =
    displayLanguage === "de"
      ? i18nT("triage.dropzone_hint", "de")
      : "Drag & drop an NDA PDF / DOCX here, or";
  const chooseFileLabel =
    displayLanguage === "de"
      ? i18nT("common.choose_file", "de")
      : "Choose file";
  const formatHint =
    displayLanguage === "de"
      ? i18nT("triage.dropzone_format_hint", "de")
      : ".pdf or .docx · English NDAs only in Phase 1";

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      className={
        "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-10 text-center transition-colors " +
        (dragOver
          ? "border-primary bg-primary/5"
          : "border-muted-foreground/25 bg-muted/20")
      }
    >
      <p className="text-sm text-muted-foreground">{dropzoneHint}</p>
      <label className="inline-flex">
        <input
          type="file"
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          onChange={handleFileInput}
          disabled={disabled}
          className="hidden"
          data-testid="triage-file-input"
        />
        <span className="cursor-pointer">
          <Button
            type="button"
            variant="outline"
            disabled={disabled}
            onClick={(e) => {
              e.preventDefault();
              const input = e.currentTarget
                .closest("label")
                ?.querySelector('input[type="file"]') as HTMLInputElement | null;
              input?.click();
            }}
          >
            {chooseFileLabel}
          </Button>
        </span>
      </label>
      <p className="text-xs text-muted-foreground">{formatHint}</p>
    </div>
  );
}

// --- DataTable ----------------------------------------------------------

interface DataTableProps {
  clauses: IngestResponseClause[];
}

function DataTable({ clauses }: DataTableProps) {
  if (clauses.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No clauses extracted. The file may be a scanned PDF with no text
        layer — see the warning banner above.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto rounded-md border">
      <table className="w-full text-sm" data-testid="triage-clauses-table">
        <thead className="bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-3 py-2 font-medium">ID</th>
            <th className="px-3 py-2 font-medium">Section</th>
            <th className="px-3 py-2 font-medium">Type</th>
            <th className="px-3 py-2 font-medium">Confidence</th>
            <th className="px-3 py-2 font-medium">Excerpt</th>
          </tr>
        </thead>
        <tbody>
          {clauses.map((c) => (
            <tr
              key={c.id}
              className="border-t align-top"
              data-testid={`triage-clause-row-${c.id}`}
            >
              <td className="px-3 py-2 font-mono text-xs">{c.id}</td>
              <td className="px-3 py-2 font-mono text-xs">
                <div>{c.position.section || "—"}</div>
                {c.position.section_title && (
                  <div className="text-[10px] text-muted-foreground">
                    {truncate(c.position.section_title, 48)}
                  </div>
                )}
              </td>
              <td className="px-3 py-2">
                <Badge
                  variant={badgeVariantForType(c.type) as never}
                  data-testid={`triage-clause-type-${c.id}`}
                >
                  {c.type}
                </Badge>
              </td>
              <td className="px-3 py-2 font-mono text-xs">
                {c.confidence.toFixed(2)}
              </td>
              <td className="px-3 py-2 text-muted-foreground">
                {truncate(c.text, 120)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- Triage page --------------------------------------------------------

export function TriagePage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  // The user's pick. "auto" is the default — the detector
  // result is the preview, the user can override.
  const [pickerValue, setPickerValue] = useState<PickerValue>("auto");
  // The detector's best-effort guess. ``null`` until a file
  // is selected. Phase 4 default is "en" (per the spec).
  const [detected, setDetected] = useState<SupportedLanguage | null>(null);
  // Phase 6: client-side clause search + per-type chip
  // filters. Both apply on top of the result set returned
  // by the backend. Empty means "no filter active". The
  // chips render only for types actually present in the
  // current result set — see ClauseFilter.
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTypes, setActiveTypes] = useState<Set<string>>(new Set());
  // Tracks the most recent ingest result identity. The
  // reset-effect compares against this ref so the
  // filter state is wiped when a fresh result set
  // arrives, but kept when the same data is re-rendered
  // (e.g. a parent re-render that didn't change the
  // ingest). Used by ``handleFile`` and the effect
  // below; declared before either so the closure order
  // is correct.
  const lastResultRef = useRef<IngestResponse | null>(null);
  // The display language for chrome strings (the i18n
  // shim looks up DE from de.json when this is "de").
  // Resolves "auto" → detected → "en" (fallback).
  const displayLanguage: SupportedLanguage = useMemo(
    () => resolveLanguage(pickerValue, detected ?? "en"),
    [pickerValue, detected],
  );

  const ingest = useMutation({
    mutationFn: async (args: { file: File; language: SupportedLanguage }): Promise<IngestResponse> => {
      const form = new FormData();
      form.append("file", args.file);
      // The backend re-detects per-clause at parse time (card
      // t_4c21627c). The form field is a *hint* — the
      // backend is the source of truth for per-clause
      // language. We send the resolved language, not the
      // picker's raw "auto" value, so the backend always
      // gets a concrete "en" | "de".
      form.append("language", args.language);
      const res = await fetch(`${API_BASE}/contracts/ingest`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(detail.detail || `HTTP ${res.status}`);
      }
      return res.json();
    },
  });

  // We resolve the language for the *current* upload at
  // submit time, not at handleFile creation time, so a
  // user who flips the picker between uploads is
  // respected. The cleanest way is to read the live state
  // via a ref-less, callback-arg pattern: the dropzone
  // gives us a File, and we read pickerValue/detected
  // directly. Both reads happen on a single render, so
  // they're consistent.
  const handleFile = useCallback(
    (file: File) => {
      setSelectedFile(file);
      // Phase 6: reset the filter state synchronously
      // when the user starts a new upload, so a stale
      // "term" query from the previous contract doesn't
      // silently carry over to the new one. The user
      // expects the page to be "fresh" for the new
      // result set. The effect below is a belt-and-
      // suspenders fallback for cases where the result
      // identity changes via a refetch (e.g. background
      // revalidation).
      setSearchQuery("");
      setActiveTypes(new Set());
      lastResultRef.current = null;
      ingest.reset();
      // Best-effort client-side sniff for the picker
      // preview. The backend re-detects at parse time —
      // the user can always override the picker. Failures
      // (binary formats where the first 2 KB decodes to
      // garbage, or FileReader unsupported) just leave the
      // previous ``detected`` value in place, which is
      // fine.
      detectLanguageFromFile(file)
        .then((lang) => {
          setDetected(lang);
        })
        .catch(() => {
          // Defensive: detectLanguageFromFile already
          // swallows errors, but keep the catch for
          // completeness.
        });
      // Submit immediately with the current picker
      // resolution. ``detected`` may still be ``null`` on
      // the first emit if the detector hasn't returned
      // yet — in that case we fall back to "en", which
      // matches the Phase 1 default behaviour exactly.
      const resolved: SupportedLanguage =
        pickerValue === "auto" ? detected ?? "en" : pickerValue;
      ingest.mutate({ file, language: resolved });
    },
    // Include pickerValue + detected in deps so the latest
    // values are read on every upload. The mutation
    // function captures the latest ``ingest`` (which is
    // stable across renders in practice) and the current
    // picker / detect state.
    [ingest, pickerValue, detected],
  );

  const result = ingest.data;
  const error = ingest.error instanceof Error ? ingest.error.message : null;

  // Phase 6: compute the filtered view of the result set.
  // Pure derivation — every render recomputes from the
  // current ``searchQuery`` + ``activeTypes`` + ``result``.
  // The filter applies case-insensitive substring match
  // against id / text / type / position.section_title.
  // Type chips apply additionally (intersection with the
  // search filter). When the result set changes (new
  // upload), the activeTypes Set is reset to a fresh
  // empty Set in the ``handleFile`` callback above; we
  // also defensively reset it here if ``result`` ever
  // changes identity, so stale filters don't survive a
  // refetch.
  const filteredClauses = useMemo(() => {
    if (!result) return [] as IngestResponseClause[];
    const q = searchQuery.trim().toLowerCase();
    return result.clauses.filter((c) => {
      // Search match — empty query lets everything through.
      if (q.length > 0) {
        const haystack = [
          c.id,
          c.text,
          c.type,
          c.position?.section_title ?? "",
        ]
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      // Type chip filter — empty Set lets everything through.
      if (activeTypes.size > 0 && !activeTypes.has(c.type)) return false;
      return true;
    });
  }, [result, searchQuery, activeTypes]);

  // Phase 6: the unique clause types present in the
  // *unfiltered* result set. The chips render one toggle
  // per type, sorted alphabetically for stable ordering
  // (so the chip row doesn't shuffle between uploads of
  // different contracts).
  const presentTypes = useMemo(() => {
    if (!result) return [] as string[];
    const set = new Set<string>();
    for (const c of result.clauses) set.add(c.type);
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [result]);

  // True iff any filter is currently active — drives the
  // "Showing N of M clauses" summary line vs the original
  // aggregate summary.
  const filterActive = searchQuery.trim().length > 0 || activeTypes.size > 0;

  // Phase 6: clear both filters. Used by the "Clear"
  // button on the search row.
  const clearFilters = useCallback(() => {
    setSearchQuery("");
    setActiveTypes(new Set());
  }, []);

  // Phase 6: toggle one type chip on/off. A new Set is
  // always returned so React's setState bails out only
  // when the value truly didn't change (no false-positive
  // re-renders).
  const toggleType = useCallback((type: string) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }, []);

  // Phase 6: when a fresh result set arrives (new upload),
  // wipe any stale filter state from the previous ingest.
  // Without this, uploading a second contract after typing
  // "term" in the search would silently carry the filter
  // over, which is surprising — the user expects the page
  // to be "fresh" for the new result. We track the
  // previous result identity in a ref; when it changes
  // (new object reference), we reset both filters.
  // A ref + effect handles the case where react-query
  // happens to return the same data object reference
  // across consecutive successful mutations (which can
  // happen with structural-sharing turned on).
  useEffect(() => {
    if (result && result !== lastResultRef.current) {
      lastResultRef.current = result;
      setSearchQuery("");
      setActiveTypes(new Set());
    }
  }, [result]);

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <main className="flex-1">
        <div className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-16">
          <header className="space-y-2">
            <h1 className="text-4xl font-bold tracking-tight">
              {displayLanguage === "de"
                ? i18nT("triage.title", "de")
                : "Triage contracts"}
            </h1>
            <p className="text-muted-foreground">
              {displayLanguage === "de"
                ? i18nT("triage.subtitle", "de")
                : "Upload an NDA, get a typed clause list back. No agents, no playbook, no redline — just the mechanical ingest → parse → classify pipeline (Phase 1)."}
            </p>
          </header>

          <Card>
            <CardHeader>
              <CardTitle>
                {displayLanguage === "de"
                  ? i18nT("triage.card_upload_title", "de")
                  : "Upload"}
              </CardTitle>
              <CardDescription>
                {displayLanguage === "de"
                  ? i18nT("triage.card_upload_description", "de")
                  : "The classifier runs without a real LLM key in Phase 1 (it falls back to a deterministic rule-based pass), so results are reproducible. Confidence reflects the classifier's certainty, not the quality of the classification."}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <LanguagePicker
                value={pickerValue}
                onChange={setPickerValue}
                displayLanguage={displayLanguage}
                detected={detected ?? undefined}
                disabled={ingest.isPending}
              />
              <Dropzone
                onFile={handleFile}
                disabled={ingest.isPending}
                displayLanguage={displayLanguage}
              />
              {selectedFile && (
                <p className="text-xs text-muted-foreground">
                  Selected: <span className="font-mono">{selectedFile.name}</span> (
                  {(selectedFile.size / 1024).toFixed(1)} KB)
                </p>
              )}
              {ingest.isPending && (
                <p className="text-sm text-muted-foreground">Triaging…</p>
              )}
              {error && (
                <div
                  className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive"
                  role="alert"
                  data-testid="triage-error"
                >
                  {error}
                </div>
              )}
            </CardContent>
          </Card>

          {result && (
            <Card>
              <CardHeader>
                <CardTitle>
                  {displayLanguage === "de"
                    ? i18nT("triage.card_results_title", "de")
                    : "Results"}
                </CardTitle>
                <CardDescription>
                  <span className="font-mono">{result.filename}</span> ·{" "}
                  {result.format.toUpperCase()} · {result.char_count} chars
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {result.is_scanned && result.scanned_warning && (
                  <div
                    className="rounded-md border border-amber-500/50 bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-300"
                    data-testid="triage-scanned-warning"
                  >
                    {result.scanned_warning}
                  </div>
                )}
                <div
                  className="flex flex-wrap gap-3 text-sm"
                  data-testid="triage-summary"
                >
                  <span>
                    <strong>{result.clause_count}</strong> clauses
                  </span>
                  <span>·</span>
                  <span>
                    <strong>{result.classified_count}</strong> classified
                  </span>
                  <span>·</span>
                  <span>
                    <strong>
                      {(result.classified_ratio * 100).toFixed(0)}%
                    </strong>{" "}
                    ratio
                  </span>
                </div>

                {/* Phase 6: client-side clause search +
                    per-type chip filter. Renders only when
                    a result is present and has at least one
                    clause (otherwise the chips row would be
                    empty and the input would be useless).
                    Sticky summary line replaces the original
                    ``triage-summary`` count when a filter is
                    active. */}
                {result.clauses.length > 0 && (
                  <div
                    className="flex flex-col gap-2"
                    data-testid="triage-filter-bar"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <input
                        type="search"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="Search clauses (id, text, type, section)…"
                        aria-label="Search clauses"
                        className="flex-1 min-w-[12rem] rounded-md border border-input bg-background px-3 py-1.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                        data-testid="triage-search-input"
                      />
                      {filterActive && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={clearFilters}
                          data-testid="triage-filter-clear"
                        >
                          Clear
                        </Button>
                      )}
                    </div>
                    {/* Type chips: one per type actually
                        present in the unfiltered result set.
                        Clicking toggles the filter; the chip
                        visually reflects its active state via
                        the Badge variant + ring outline. */}
                    {presentTypes.length > 0 && (
                      <div
                        className="flex flex-wrap gap-1.5"
                        data-testid="triage-type-filter-row"
                      >
                        {presentTypes.map((t) => {
                          const active = activeTypes.has(t);
                          return (
                            <button
                              key={t}
                              type="button"
                              onClick={() => toggleType(t)}
                              aria-pressed={active}
                              className={
                                "rounded-full transition focus:outline-none focus:ring-2 focus:ring-ring " +
                                (active
                                  ? "ring-2 ring-primary"
                                  : "opacity-70 hover:opacity-100")
                              }
                              data-testid={`triage-type-filter-${t}`}
                            >
                              <Badge
                                variant={
                                  badgeVariantForType(t) as never
                                }
                              >
                                {t}
                              </Badge>
                            </button>
                          );
                        })}
                      </div>
                    )}
                    {/* Filter summary replaces the implicit
                        "all visible" state when a filter is
                        active. Hidden when no filter — the
                        original ``triage-summary`` (clause
                        count / classified count / ratio)
                        already tells the user the totals. */}
                    {filterActive && (
                      <p
                        className="text-xs text-muted-foreground"
                        data-testid="triage-filter-summary"
                      >
                        Showing <strong>{filteredClauses.length}</strong>{" "}
                        of <strong>{result.clauses.length}</strong>{" "}
                        clauses
                        {searchQuery.trim().length > 0 && (
                          <>
                            {" "}
                            matching <span className="font-mono">
                              "{searchQuery.trim()}"
                            </span>
                          </>
                        )}
                        {activeTypes.size > 0 && (
                          <>
                            {" "}
                            in{" "}
                            <span className="font-mono">
                              {Array.from(activeTypes).sort().join(", ")}
                            </span>
                          </>
                        )}
                      </p>
                    )}
                  </div>
                )}

                <DataTable clauses={filteredClauses} />
              </CardContent>
            </Card>
          )}
        </div>
      </main>
      <DisclaimerFooter />
    </div>
  );
}

export default TriagePage;
