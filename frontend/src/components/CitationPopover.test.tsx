import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CitationPopover, truncateExcerpt } from "@/components/CitationPopover";

// CitationPopover: shows the cited baseline + the contract
// excerpt. Renders "(no citation)" placeholder for unverified
// / missing citations, never crashes on either.

const SAMPLE_CITATION = {
  playbook_clause_id: "nda-en::term::001",
  contract_text_excerpt:
    "The obligations of confidentiality shall continue for a period of three (3) years from the Effective Date.",
  source_url: "https://example.com/baseline/term",
};

describe("CitationPopover", () => {
  it("renders the trigger button for a cited flag", () => {
    render(<CitationPopover citation={SAMPLE_CITATION} />);
    const trigger = screen.getByTestId("citation-popover-trigger");
    expect(trigger).toHaveTextContent("View citation");
    expect(trigger).toHaveAttribute("data-citation-state", "cited");
    expect(trigger).not.toBeDisabled();
  });

  it("renders the panel with excerpt + source URL on click", async () => {
    const user = userEvent.setup();
    render(<CitationPopover citation={SAMPLE_CITATION} />);
    await user.click(screen.getByTestId("citation-popover-trigger"));
    const panel = screen.getByTestId("citation-popover-panel");
    expect(panel).toHaveAttribute("data-citation-state", "cited");
    expect(screen.getByTestId("citation-playbook-id")).toHaveTextContent(
      "nda-en::term::001"
    );
    expect(screen.getByTestId("citation-excerpt")).toHaveTextContent(
      /three \(3\) years/
    );
    const link = screen.getByTestId("citation-source-url");
    expect(link).toHaveAttribute("href", "https://example.com/baseline/term");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("truncates the contract excerpt at the 200-char limit with an ellipsis", async () => {
    const longExcerpt = "a".repeat(500);
    const user = userEvent.setup();
    render(
      <CitationPopover
        citation={{
          ...SAMPLE_CITATION,
          contract_text_excerpt: longExcerpt,
        }}
      />
    );
    await user.click(screen.getByTestId("citation-popover-trigger"));
    const excerpt = screen.getByTestId("citation-excerpt");
    // 199 a's + 1 ellipsis char (U+2026 "…")
    expect(excerpt.textContent?.length).toBe(200);
    expect(excerpt.textContent?.endsWith("…")).toBe(true);
  });

  it("renders the trigger in the 'unverified' state when unverified=true", () => {
    render(
      <CitationPopover citation={SAMPLE_CITATION} unverified={true} />
    );
    const trigger = screen.getByTestId("citation-popover-trigger");
    expect(trigger).toHaveTextContent(/unverified/);
    expect(trigger).toHaveAttribute("data-citation-state", "unverified");
    // Still opens — the user can read the citation even on
    // unverified flags.
    expect(trigger).not.toBeDisabled();
  });

  it("renders the trigger in the 'missing' state when citation is null", () => {
    render(<CitationPopover citation={null} />);
    const trigger = screen.getByTestId("citation-popover-trigger");
    expect(trigger).toHaveTextContent("No citation");
    expect(trigger).toHaveAttribute("data-citation-state", "missing");
    // Disabled — the user can't open a panel that has nothing in it.
    expect(trigger).toBeDisabled();
  });

  it("renders the trigger in the 'missing' state when citation is undefined", () => {
    render(<CitationPopover citation={undefined} />);
    const trigger = screen.getByTestId("citation-popover-trigger");
    expect(trigger).toHaveTextContent("No citation");
    expect(trigger).toBeDisabled();
  });

  it("renders without a panel until the trigger is clicked (no crash on mount)", () => {
    render(<CitationPopover citation={SAMPLE_CITATION} />);
    expect(screen.queryByTestId("citation-popover-panel")).toBeNull();
  });

  it("closes the panel when the close (×) button is clicked", async () => {
    const user = userEvent.setup();
    render(<CitationPopover citation={SAMPLE_CITATION} />);
    await user.click(screen.getByTestId("citation-popover-trigger"));
    expect(screen.getByTestId("citation-popover-panel")).toBeInTheDocument();
    await user.click(screen.getByTestId("citation-popover-close"));
    expect(screen.queryByTestId("citation-popover-panel")).toBeNull();
  });
});

describe("truncateExcerpt", () => {
  it("returns the text unchanged when under the limit", () => {
    expect(truncateExcerpt("hello", 10)).toBe("hello");
  });

  it("trims whitespace before measuring", () => {
    expect(truncateExcerpt("   hello   ", 100)).toBe("hello");
  });

  it("truncates with an ellipsis when over the limit", () => {
    const out = truncateExcerpt("a".repeat(250), 200);
    expect(out.endsWith("…")).toBe(true);
    expect(out.length).toBe(200);
  });
});
