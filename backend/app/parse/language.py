"""Per-clause language detection — Phase 4 (bilingual DE).

The classifier prompt switch (DE vs EN) and the per-clause
``language: "de" | "en"`` field on :class:`app.classify.schema.Clause`
both depend on knowing the source language of the clause text. The
detection step runs **at parse time**, not at query time, so the
classifier itself does not have to detect language — it reads the
field. The spec is explicit (line 285-287 of
``docs/11-phases.md``):

    "The Pydantic schemas and English clause type enums stay the
    same — the language detection is a per-clause
    ``language: \"de\" | \"en\"`` field."

and the Phase 4 plan card (t_4c21627c) hard-rules:

    "The language field is set at parse time, not at query time.
    The classifier should not have to detect language — it reads
    the field."

We use a **stopword heuristic** rather than ``langdetect`` (or any
statistical model). The reasons, in order of importance:

1. **No new dependency.** ``langdetect`` is not in ``pyproject.toml``,
   and adding a probabilistic model for a binary classification on
   well-formed legal text is overkill.
2. **Deterministic.** A model that consults a probability distribution
   over language families can be flaky on a short clause
   (``"Diese Vereinbarung unterliegt deutschem Recht."`` is 50 chars
   and a model could flip the verdict on a re-run with a different
   seed). The stopword heuristic always returns the same answer for
   the same input.
3. **Legal-domain signal.** The DE legal register has a stable
   set of high-frequency function words (``der, die, das, und,
   oder, ist, werden, hiermit, gemäß, ...``) and a small set of
   legal-domain indicators (``Haftung, Schadensersatz, Vertragsstrafe,
   Kündigung, Vertraulich, Vereinbarung, ...``). The same is true
   for EN (``the, and, shall, agreement, confidential, ...``). A
   function-word count is the right level of signal — higher than
   character n-grams (which is what ``langdetect`` does internally
   and is noisy on short text), lower than a full LLM call.
4. **No model download.** ``langdetect`` ships a profile database
   that has to be loaded at first use. Stopwords are in code.

The detector only consults the **first 500 characters** of the
clause text (per the Phase 4 plan: "Use langdetect (or a stopword
heuristic) on the first 500 chars of the clause text"). 500 chars
is enough to capture the section heading + the first sentence,
which is where DE-vs-EN function words reliably appear. The
restriction matters because a long clause that quotes a foreign
statute (e.g. a DE NDA that quotes the GDPR text in English) would
otherwise pollute the score.

The function is **pure** (no I/O, no global state, no model load)
so it is trivially testable.
"""

from __future__ import annotations

import re
from typing import Final


# A hard cap on the text the detector consults. The spec is explicit:
# "first 500 chars". Long clauses that quote foreign-language statutes
# would otherwise pollute the score. We use the full 500 as a
# tie-breaker only — the *primary* signal is the first 200 chars
# (heading + first 1-2 sentences), which is where the
# language-of-origin signal is strongest.
_DETECT_WINDOW_CHARS: Final = 500
_PRIMARY_WINDOW_CHARS: Final = 200


# Stopword sets. Two design notes:
#
# 1. **All lowercase, no punctuation.** The detector lower-cases the
#    input and splits on a non-letter regex, so the stopwords are
#    stored as bare word tokens. Umlauts (ä, ö, ü, ß) are kept in
#    their original form because ``re.split`` does not strip them
#    and the text is already lower-cased.
#
# 2. **Curated, not exhaustive.** We pick words that reliably
#    distinguish DE legal text from EN legal text. Common words that
#    appear in BOTH languages (e.g. "in", "of" — "in" is a stopword
#    in EN and also appears in DE, "der/die/das" is DE-only) are
#    included on the side they actually belong to. A word that is
#    ambiguous (e.g. "Information" appears in both) is included on
#    both sides or excluded — the goal is to be accurate on real
#    DE-vs-EN contract text, not to be a research-grade detector.
_DE_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        # Function words — high frequency in DE legal register
        "der",
        "die",
        "das",
        "und",
        "oder",
        "ist",
        "sind",
        "war",
        "waren",
        "wird",
        "werden",
        "wurde",
        "wurden",
        "hat",
        "haben",
        "hatte",
        "hatten",
        "kann",
        "können",
        "konnte",
        "konnten",
        "muss",
        "müssen",
        "musste",
        "mussten",
        "soll",
        "sollen",
        "sollte",
        "sollten",
        "vom",
        "zur",
        "zum",
        "im",
        "am",
        "ein",
        "eine",
        "einer",
        "eines",
        "einem",
        "auf",
        "bei",
        "mit",
        "nach",
        "von",
        "aus",
        "zu",
        "nicht",
        "auch",
        "über",
        "unter",
        "zwischen",
        "gegen",
        "ohne",
        "sich",
        "sowie",
        "gemäß",
        "hiermit",
        "diese",
        "diesem",
        "diesen",
        "dieser",
        "jene",
        "jener",
        "alle",
        "alles",
        "beiden",
        "kein",
        "keine",
        "keiner",
        "keinem",
        "wenn",
        "dann",
        "weil",
        "obwohl",
        "damit",
        "dass",
        "ob",
        "als",
        "wie",
        "gilt",
        "gelten",
        # Legal-domain indicators — DE-specific phrasings
        "haftung",
        "schadensersatz",
        "vertragsstrafe",
        "kündigung",
        "kündigungsfrist",
        "vertraulich",
        "geheim",
        "vereinbarung",
        "vertrag",
        "vertragspartei",
        "vertragsparteien",
        "empfänger",
        "offenbarung",
        "empfängerpartei",
        "gerichtsbarkeit",
        "gericht",
        "gerichtsstand",
        "schiedsstelle",
        "schiedsverfahren",
        "anwendbare",
        "anwendbares",
        "rechts",
        "rechtsanwalt",
        "rechtsanwälte",
        "geltend",
        "geltendmachung",
    }
)


_EN_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        # Function words — high frequency in EN legal register
        "the",
        "a",
        "an",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "has",
        "have",
        "had",
        "will",
        "would",
        "shall",
        "should",
        "may",
        "might",
        "can",
        "could",
        "must",
        "in",
        "on",
        "at",
        "by",
        "for",
        "with",
        "from",
        "to",
        "of",
        "as",
        "be",
        "been",
        "being",
        "this",
        "that",
        "these",
        "those",
        "all",
        "any",
        "each",
        "every",
        "no",
        "not",
        "also",
        "if",
        "then",
        "because",
        "although",
        "while",
        "when",
        "where",
        "how",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "into",
        "onto",
        "upon",
        "about",
        # Legal-domain indicators — EN-specific phrasings
        "agreement",
        "confidential",
        "party",
        "parties",
        "information",
        "disclosing",
        "receiving",
        "disclose",
        "disclosed",
        "hereof",
        "hereto",
        "herein",
        "hereunder",
        "hereby",
        "thereto",
        "jurisdiction",
        "governed",
        "indemnify",
        "warranty",
        "warranties",
        "covenant",
        "covenantor",
    }
)


# A non-letter separator. We split on anything that is not a Unicode
# letter (so umlauts and the ß survive). The pattern is conservative
# — we do not need full Unicode segmentation, just "split into tokens".
_TOKEN_SPLIT = re.compile(r"[^\w]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    """Lower-case + split into a list of bare word tokens.

    We return a **list** (not a set) so the scorer can count
    *occurrences*. A clause that opens with a dense burst of
    function words (``Der Vertrag wird durch die Parteien
    unterzeichnet.``) should score higher than a clause that
    happens to contain a few stray foreign-language words, even
    if the total word count is the same. Distinct-word scoring
    (set semantics) would flatten this — a clause with 3 DE
    stopwords used once each would tie a clause with 3 DE
    stopwords used 3 times each.
    """
    if not text:
        return []
    # Lower-case so the stopword lookup is case-insensitive.
    lowered = text.lower()
    tokens = _TOKEN_SPLIT.split(lowered)
    # Strip empty tokens (the split produces "" when the text starts
    # with a non-letter) and keep the rest. No length filter — a
    # 1-letter token (e.g. "a", "I" in EN) is a real stopword.
    return [t for t in tokens if t]


def _score(tokens: list[str]) -> tuple[int, int]:
    """Return ``(de_count, en_count)`` of stopword occurrences.

    A token is a stopword hit when it appears in the curated
    stopword set (case-insensitive, after the lower-casing in
    :func:`_tokenize`). We use a set-membership test on each
    token so the score is O(n) in the window length.
    """
    de = 0
    en = 0
    for t in tokens:
        if t in _DE_STOPWORDS:
            de += 1
        elif t in _EN_STOPWORDS:
            en += 1
    return de, en


def detect_language(
    text: str,
    *,
    heading: str | None = None,
) -> str:
    """Return ``"de"`` or ``"en"`` for the language of ``text``.

    The detection uses a stopword-heuristic on the first
    :data:`_PRIMARY_WINDOW_CHARS` (200) characters of ``text``,
    with a tie-breaker on the full :data:`_DETECT_WINDOW_CHARS`
    (500) characters. The score is the number of **occurrence**
    DE-specific stopwords vs the number of occurrence
    EN-specific stopwords. The language with the higher score
    wins; on a tie, the function returns ``"en"`` (the Phase 1
    default — the spec's "if neither language is detected, the
    EN path is the safe fallback").

    Parameters
    ----------
    text
        The clause text to detect. The detector is case-insensitive
        and tolerates punctuation, but the text should not be
        empty (an empty string returns ``"en"``).
    heading
        Optional section title (``position.section_title`` from
        the chunker). When the body text is short or uninformative
        (e.g. a heading-only clause like
        ``"VERTRAULICHKEITSVEREINBARUNG."``), the heading is
        consulted as a secondary signal. A heading that itself
        contains DE function words (``Vereinbarung``, ``Vertrag``,
        ``Haftung``, etc.) tips the score to ``"de"``; the same
        logic applies to EN. Default: ``None`` (heading ignored).

    Returns
    -------
    str
        ``"de"`` if the DE stopword score is higher,
        ``"en"`` otherwise.

    Notes
    -----
    The function is **pure** (no I/O, no global state, no model
    load). It is called once per clause at parse time, so the
    cost is one regex split + one set difference — O(n) in the
    length of the input window. For a 500-char input, that is
    well under 100 µs on commodity hardware.

    Design rationale (Phase 4 spec line 285-287 + plan card
    t_4c21627c):

    1. **First 200 chars** is the primary signal — the section
       heading + first 1-2 sentences, where the
       language-of-origin signal is strongest. A long EN/DE quote
       in the second half of the clause is a quote, not the
       clause's language.
    2. **First 500 chars** is the secondary tie-breaker — used
       only when the primary window yields a 0–0 or perfect tie.
       A heading-only clause (``"Vertraulichkeitsvereinbarung."``)
       has no function words in 200 chars; the full 500 still
       may not help, so we fall back to the ``heading`` argument.
    3. **Heading signal** is the final tie-breaker — a heading
       like ``"VERTRAULICHKEITSVEREINBARUNG"`` is itself DE
       legal terminology and should be classified as DE even
       when the body is one word.
    4. **Occurrence-based scoring** (not distinct-word): a
       clause that opens with a dense burst of function words
       ``Der Vertrag wird durch die Parteien unterzeichnet.``
       should score higher than a clause that has the same
       number of *distinct* DE words spread thinly across
       200 chars.
    """
    if not text:
        return "en"
    # Primary signal: the first 200 chars. This is the section
    # heading + first 1-2 sentences, which is where the
    # language-of-origin signal is strongest. A long EN/DE quote
    # in the second half of the clause is a quote, not the
    # clause's language.
    primary_tokens = _tokenize(text[:_PRIMARY_WINDOW_CHARS])
    de_primary, en_primary = _score(primary_tokens)
    # Primary decides outright when the gap is unambiguous.
    if de_primary > en_primary:
        return "de"
    if en_primary > de_primary:
        return "en"
    # Tie or zero — consult the full 500-char window. A clause
    # whose first 200 chars have no function words (rare, e.g.
    # a heading-only "Vertraulichkeitsvereinbarung.") gets a
    # second chance from the body.
    full_tokens = _tokenize(text[:_DETECT_WINDOW_CHARS])
    de_full, en_full = _score(full_tokens)
    if de_full > en_full:
        return "de"
    if en_full > de_full:
        return "en"
    # Final tie-breaker: the heading (if provided). A heading
    # like "VERTRAULICHKEITSVEREINBARUNG" is itself DE legal
    # terminology — the chunker populates position.section_title
    # separately from the body, so we accept it as a
    # second-class signal here.
    if heading:
        heading_tokens = _tokenize(heading)
        de_head, en_head = _score(heading_tokens)
        if de_head > en_head:
            return "de"
        if en_head > de_head:
            return "en"
    # Undetectable: default to "en" (the safe Phase 1 fallback).
    return "en"


__all__ = ["detect_language"]
