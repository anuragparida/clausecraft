import { describe, it, expect } from "vitest";
import { detectLanguage } from "@/lib/detectLanguage";

// Unit tests for the client-side language detector.
//
// What we test:
//   1. A clearly English NDA-style text snippet is detected
//      as "en".
//   2. A clearly German NDA-style text snippet is detected
//      as "de".
//   3. Empty / very short / tied input falls back to "en"
//      (Phase 4 default; the picker lets the user override).
//   4. EN text that *mentions* German terms (loanwords) is
//      still detected as "en" — the heuristic is robust to
//      the "Vertraulichkeitsvereinbarung" case the spec
//      calls out.

describe("detectLanguage", () => {
  it("detects a clearly English NDA snippet as 'en'", () => {
    const text = [
      "This Mutual Non-Disclosure Agreement (this Agreement) is entered",
      "into as of the Effective Date by and between the parties.",
      "Each party agrees that the Confidential Information of the",
      "other party shall not be disclosed to any third party and",
      "shall be used solely for the purpose of evaluating the",
      "transaction. The obligations of confidentiality shall",
      "survive the termination of this Agreement for a period of",
      "five years. This Agreement shall be governed by the laws",
      "of the State of Delaware.",
    ].join(" ");
    expect(detectLanguage(text)).toBe("en");
  });

  it("detects a clearly German NDA snippet as 'de'", () => {
    const text = [
      "Diese Vertraulichkeitsvereinbarung wird zwischen den",
      "Parteien mit Wirkung zum Datum des Vertragsabschlusses",
      "geschlossen. Die Parteien verpflichten sich, die",
      "vertraulichen Informationen der anderen Partei nicht an",
      "Dritte weiterzugeben und diese ausschließlich für die",
      "Bewertung der Transaktion zu verwenden. Die",
      "Vertraulichkeitsverpflichtungen gelten über die Beendigung",
      "dieser Vereinbarung hinaus für einen Zeitraum von fünf",
      "Jahren. Diese Vereinbarung unterliegt deutschem Recht.",
    ].join(" ");
    expect(detectLanguage(text)).toBe("de");
  });

  it("returns 'en' for empty input", () => {
    expect(detectLanguage("")).toBe("en");
  });

  it("returns 'en' for very short input (< 20 tokens)", () => {
    // Even all-German: not enough signal at this size.
    expect(detectLanguage("der die das und oder nicht")).toBe("en");
  });

  it("returns 'en' when DE and EN stopword counts tie", () => {
    // Constructed so each side has 5 hits out of 10 tokens.
    // The remaining 5 tokens are pure noise that hits neither set.
    const text =
      "the und of der to die in das and ein or das the und der of";
    expect(detectLanguage(text)).toBe("en");
  });

  it("returns 'en' when both stopword counts are zero (gibberish)", () => {
    const text = "xxxxxxxxxx yyyyyyyy zzzzzzzzzz aaaaaaaaaa bbbbbbbbbb";
    expect(detectLanguage(text)).toBe("en");
  });

  it("is robust to an English NDA that quotes a German term in passing", () => {
    // The Phase 4 spec calls out that EN NDAs may contain
    // German loanwords ("Vertraulichkeitsvereinbarung").
    // The detector should still pick EN.
    const text = [
      "This Agreement, sometimes referred to as a",
      "Vertraulichkeitsvereinbarung, is entered into as of the",
      "Effective Date. Each party agrees that the Confidential",
      "Information of the other party shall not be disclosed",
      "and shall be used solely for the purpose of evaluating",
      "the transaction. The obligations shall survive the",
      "termination of this Agreement for a period of five",
      "years. This Agreement shall be governed by the laws of",
      "the State of Delaware.",
    ].join(" ");
    expect(detectLanguage(text)).toBe("en");
  });

  it("preserves umlauts and ß as part of the token", () => {
    // The tokeniser is Unicode-aware, so "müssen" / "höhere"
    // / "große" should be matched as a single token against
    // the DE stopword set. If the tokeniser dropped the
    // umlaut, the hit would not register.
    const text = [
      "Die Parteien müssen die vertraulichen Informationen",
      "der anderen Partei schützen. Eine höhere Strafe ist",
      "nicht vorgesehen, aber das Gericht kann eine große",
      "Entschädigung festsetzen. Die Verpflichtungen gelten",
      "auch nach Beendigung dieser Vereinbarung für fünf",
      "Jahre weiter. Diese Vereinbarung unterliegt",
      "deutschem Recht und wird in Köln unterzeichnet.",
    ].join(" ");
    expect(detectLanguage(text)).toBe("de");
  });
});
