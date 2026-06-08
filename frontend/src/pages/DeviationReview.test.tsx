import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  DeviationReviewPage,
  SAMPLE_DEVIATION_REVIEW_DATA,
  type DeviationFlag,
  type DeviationReviewData,
} from "@/pages/DeviationReview";

// DeviationReview: renders 0 / 1 / N flags without crash. Approve
// / Reject / Edit mutate local state. "No baseline" rows get a
// distinct muted treatment. Counterparty matrix verdict column
// shows the flat baseline verdict.

function makeFlag(over: Partial<DeviationFlag> = {}): DeviationFlag {
  return {
    clause_id: "c1",
    score: 1,
    rationale: "Default rationale",
    citation: {
      playbook_clause_id: "nda-en::term::001",
      contract_text_excerpt: "The term shall be 3 years.",
    },
    unverified: false,
    baseline_type: "term",
    ...over,
  };
}

function makeData(flags: DeviationFlag[]): DeviationReviewData {
  return {
    filename: "test-nda.pdf",
    flag_count: flags.length,
    flagged_count: flags.filter((f) => f.score > 0).length,
    unverified_count: flags.filter((f) => f.unverified).length,
    no_baseline_count: flags.filter(
      (f) => f.unverified && f.rationale.trim().toLowerCase() === "no matching playbook clause"
    ).length,
    matrix_version: "phase2-flat",
    embedding_provider: "stub",
    flags,
  };
}

const NO_BASELINE_FLAG = makeFlag({
  clause_id: "c2",
  score: 0,
  rationale: "no matching playbook clause",
  citation: null,
  unverified: true,
  baseline_type: "",
});

const RENDER_PROPS = {
  onBackToHome: () => {},
  onBackToTriage: () => {},
};

describe("DeviationReviewPage", () => {
  it("renders zero flags without crashing", () => {
    render(
      <DeviationReviewPage
        {...RENDER_PROPS}
        data={makeData([])}
      />
    );
    // Empty state message visible.
    expect(screen.getByTestId("deviation-review-empty")).toBeInTheDocument();
    // No table on the page when flags=[].
    expect(screen.queryByTestId("deviation-review-table")).toBeNull();
  });

  it("renders the loading state when loading=true", () => {
    render(<DeviationReviewPage {...RENDER_PROPS} loading />);
    expect(screen.getByText(/Loading flags/)).toBeInTheDocument();
  });

  it("renders the error state when error is provided", () => {
    render(
      <DeviationReviewPage {...RENDER_PROPS} error="Spotter unreachable" />
    );
    const alert = screen.getByTestId("deviation-review-error");
    expect(alert).toHaveTextContent("Spotter unreachable");
  });

  it("renders one flag without crashing", () => {
    const data = makeData([makeFlag()]);
    render(<DeviationReviewPage {...RENDER_PROPS} data={data} />);
    expect(screen.getByTestId("deviation-review-table")).toBeInTheDocument();
    expect(screen.getByTestId("deviation-row-c1")).toBeInTheDocument();
  });

  it("renders N flags (5) without crashing — every clause gets a row", () => {
    const data = makeData(
      [0, 1, 2, 3].map((score, i) =>
        makeFlag({
          clause_id: `c${i + 1}`,
          score,
          rationale: `Rationale for clause ${i + 1}`,
        })
      ).concat([makeFlag({ clause_id: "c5", score: 2 })])
    );
    render(<DeviationReviewPage {...RENDER_PROPS} data={data} />);
    for (const id of ["c1", "c2", "c3", "c4", "c5"]) {
      expect(screen.getByTestId(`deviation-row-${id}`)).toBeInTheDocument();
    }
  });

  it("renders the sample data fixture shipped with the page", () => {
    render(
      <DeviationReviewPage
        {...RENDER_PROPS}
        data={SAMPLE_DEVIATION_REVIEW_DATA}
      />
    );
    expect(screen.getByTestId("deviation-row-c1")).toBeInTheDocument();
    expect(screen.getByTestId("deviation-row-c2")).toBeInTheDocument();
  });

  it("renders a SeverityBadge for each non-no-baseline row with the right score", () => {
    const data = makeData([
      makeFlag({ clause_id: "c1", score: 0 }),
      makeFlag({ clause_id: "c2", score: 2 }),
      makeFlag({ clause_id: "c3", score: 3 }),
    ]);
    render(<DeviationReviewPage {...RENDER_PROPS} data={data} />);
    const row1 = screen.getByTestId("deviation-row-c1");
    const row2 = screen.getByTestId("deviation-row-c2");
    const row3 = screen.getByTestId("deviation-row-c3");
    expect(within(row1).getByTestId("severity-badge")).toHaveAttribute(
      "data-severity",
      "0"
    );
    expect(within(row2).getByTestId("severity-badge")).toHaveAttribute(
      "data-severity",
      "2"
    );
    expect(within(row3).getByTestId("severity-badge")).toHaveAttribute(
      "data-severity",
      "3"
    );
  });

  it("renders a 'no baseline' badge for unverified no-baseline rows", () => {
    const data = makeData([NO_BASELINE_FLAG]);
    render(<DeviationReviewPage {...RENDER_PROPS} data={data} />);
    const row = screen.getByTestId("deviation-row-c2");
    expect(row).toHaveAttribute("data-no-baseline", "true");
    expect(
      within(row).getByTestId("flag-no-baseline-badge-c2")
    ).toHaveTextContent("no baseline");
  });

  it("renders the matrix verdict column with the flat baseline verdict", () => {
    const data = makeData([
      makeFlag({ clause_id: "c1", score: 1 }),
      makeFlag({ clause_id: "c2", score: 3 }),
    ]);
    render(<DeviationReviewPage {...RENDER_PROPS} data={data} />);
    expect(
      screen.getByTestId("flag-matrix-verdict-c1")
    ).toHaveAttribute("data-matrix-verdict", "minor");
    expect(
      screen.getByTestId("flag-matrix-verdict-c1")
    ).toHaveTextContent("minor");
    expect(
      screen.getByTestId("flag-matrix-verdict-c2")
    ).toHaveAttribute("data-matrix-verdict", "unacceptable");
  });

  it("Approve button mutates the local action state for the row", async () => {
    const user = userEvent.setup();
    const data = makeData([makeFlag()]);
    render(<DeviationReviewPage {...RENDER_PROPS} data={data} />);
    const row = screen.getByTestId("deviation-row-c1");
    // Pre-state: data-flag-action="none"
    expect(row).toHaveAttribute("data-flag-action", "none");
    await user.click(screen.getByTestId("flag-approve-c1"));
    // Post-state: data-flag-action="approved"
    expect(row).toHaveAttribute("data-flag-action", "approved");
  });

  it("Reject button mutates the local action state for the row", async () => {
    const user = userEvent.setup();
    const data = makeData([makeFlag()]);
    render(<DeviationReviewPage {...RENDER_PROPS} data={data} />);
    const row = screen.getByTestId("deviation-row-c1");
    expect(row).toHaveAttribute("data-flag-action", "none");
    await user.click(screen.getByTestId("flag-reject-c1"));
    expect(row).toHaveAttribute("data-flag-action", "rejected");
  });

  it("Edit button opens an inline text input; Save persists the new rationale", async () => {
    const user = userEvent.setup();
    const data = makeData([
      makeFlag({ clause_id: "c1", rationale: "original rationale" }),
    ]);
    render(<DeviationReviewPage {...RENDER_PROPS} data={data} />);
    const row = screen.getByTestId("deviation-row-c1");
    // Pre-edit: the rationale cell shows the original text.
    expect(
      within(row).getByTestId("flag-rationale-c1")
    ).toHaveTextContent("original rationale");

    await user.click(screen.getByTestId("flag-edit-c1"));
    // After click: the inline input appears.
    const input = screen.getByTestId("flag-edit-input-c1");
    expect(input).toBeInTheDocument();
    // The input is pre-seeded with the original rationale.
    expect(input).toHaveValue("original rationale");

    // Type a new value and save.
    await user.clear(input);
    await user.type(input, "revised rationale");
    await user.click(screen.getByTestId("flag-save-edit-c1"));

    // The rationale cell now shows the new text.
    expect(
      within(row).getByTestId("flag-rationale-c1")
    ).toHaveTextContent("revised rationale");
    // The row's flag-action is "edited".
    expect(row).toHaveAttribute("data-flag-action", "edited");
    // The inline input is gone.
    expect(screen.queryByTestId("flag-edit-input-c1")).toBeNull();
  });

  it("Edit → Cancel restores the prior rationale", async () => {
    const user = userEvent.setup();
    const data = makeData([
      makeFlag({ clause_id: "c1", rationale: "original" }),
    ]);
    render(<DeviationReviewPage {...RENDER_PROPS} data={data} />);
    await user.click(screen.getByTestId("flag-edit-c1"));
    const input = screen.getByTestId("flag-edit-input-c1");
    await user.clear(input);
    await user.type(input, "should not stick");
    await user.click(screen.getByTestId("flag-cancel-edit-c1"));

    const row = screen.getByTestId("deviation-row-c1");
    expect(
      within(row).getByTestId("flag-rationale-c1")
    ).toHaveTextContent("original");
    expect(row).toHaveAttribute("data-flag-action", "none");
  });

  it("Approve / Reject / Edit are independent per row", async () => {
    const user = userEvent.setup();
    const data = makeData([
      makeFlag({ clause_id: "c1" }),
      makeFlag({ clause_id: "c2" }),
    ]);
    render(<DeviationReviewPage {...RENDER_PROPS} data={data} />);
    await user.click(screen.getByTestId("flag-approve-c1"));
    expect(screen.getByTestId("deviation-row-c1")).toHaveAttribute(
      "data-flag-action",
      "approved"
    );
    expect(screen.getByTestId("deviation-row-c2")).toHaveAttribute(
      "data-flag-action",
      "none"
    );
  });

  it("renders the back-to-home button and calls the handler on click", async () => {
    const user = userEvent.setup();
    let homeClicks = 0;
    render(
      <DeviationReviewPage
        data={makeData([makeFlag()])}
        onBackToHome={() => {
          homeClicks++;
        }}
        onBackToTriage={() => {}}
      />
    );
    await user.click(screen.getByTestId("deviation-back-home"));
    expect(homeClicks).toBe(1);
  });

  it("hides the back-to-triage button when onBackToTriage is not provided", () => {
    render(
      <DeviationReviewPage
        data={makeData([makeFlag()])}
        onBackToHome={() => {}}
      />
    );
    expect(screen.queryByTestId("deviation-back-triage")).toBeNull();
  });

  // --- Add-context flow -------------------------------------------------

  it("Add context button opens a textarea; Save persists the context", async () => {
    const user = userEvent.setup();
    const data = makeData([makeFlag({ clause_id: "c1" })]);
    render(<DeviationReviewPage {...RENDER_PROPS} data={data} />);
    const row = screen.getByTestId("deviation-row-c1");
    await user.click(screen.getByTestId("flag-add-context-c1"));
    const input = screen.getByTestId("flag-context-input-c1");
    expect(input).toBeInTheDocument();
    await user.type(input, "acceptable for our use case");
    await user.click(screen.getByTestId("flag-save-context-c1"));
    // The rationale cell renders the saved context in a
    // dedicated block.
    expect(
      within(row).getByTestId("flag-context-cell-c1"),
    ).toHaveTextContent("acceptable for our use case");
    // The button now reads "context saved" (a small marker).
    expect(
      within(row).getByTestId("flag-context-saved-c1"),
    ).toHaveTextContent("context saved");
  });

  it("Add context → Cancel reverts the row to no-context state", async () => {
    const user = userEvent.setup();
    const data = makeData([makeFlag({ clause_id: "c1" })]);
    render(<DeviationReviewPage {...RENDER_PROPS} data={data} />);
    await user.click(screen.getByTestId("flag-add-context-c1"));
    const input = screen.getByTestId("flag-context-input-c1");
    await user.type(input, "should not stick");
    await user.click(screen.getByTestId("flag-cancel-context-c1"));
    expect(screen.queryByTestId("flag-context-input-c1")).toBeNull();
    expect(
      screen.queryByTestId("flag-context-cell-c1"),
    ).not.toBeInTheDocument();
  });

  // --- Generate-redline gating -----------------------------------------

  it("Generate redline button is hidden when showGenerateRedline=false (default)", () => {
    const data = makeData([makeFlag()]);
    render(<DeviationReviewPage {...RENDER_PROPS} data={data} />);
    expect(screen.queryByTestId("generate-redline-bar")).toBeNull();
  });

  it("Generate redline button is disabled while any flag is undecided", () => {
    const data = makeData([
      makeFlag({ clause_id: "c1" }),
      makeFlag({ clause_id: "c2" }),
    ]);
    render(
      <DeviationReviewPage
        {...RENDER_PROPS}
        data={data}
        showGenerateRedline
      />,
    );
    const button = screen.getByTestId("generate-redline-button");
    expect(button).toBeDisabled();
    expect(
      screen.getByTestId("generate-redline-status"),
    ).toHaveTextContent(/Decide every flag/);
  });

  it("Generate redline button is enabled once every flag is decided", async () => {
    const user = userEvent.setup();
    const data = makeData([
      makeFlag({ clause_id: "c1" }),
      makeFlag({ clause_id: "c2" }),
    ]);
    render(
      <DeviationReviewPage
        {...RENDER_PROPS}
        data={data}
        showGenerateRedline
      />,
    );
    await user.click(screen.getByTestId("flag-approve-c1"));
    await user.click(screen.getByTestId("flag-reject-c2"));
    const button = screen.getByTestId("generate-redline-button");
    expect(button).toBeEnabled();
    expect(
      screen.getByTestId("generate-redline-status"),
    ).toHaveTextContent(/Every flag has a decision/);
  });

  it("Generate redline calls onSubmitDecisions with the user's batch", async () => {
    const user = userEvent.setup();
    const data = makeData([
      makeFlag({ clause_id: "c1" }),
      makeFlag({ clause_id: "c2" }),
    ]);
    let submitted: Array<{ clause_id: string; decision: string }> = [];
    render(
      <DeviationReviewPage
        {...RENDER_PROPS}
        data={data}
        showGenerateRedline
        onSubmitDecisions={(batch) => {
          submitted = batch.map((b) => ({
            clause_id: b.clause_id,
            decision: b.decision,
          }));
        }}
      />,
    );
    await user.click(screen.getByTestId("flag-approve-c1"));
    await user.click(screen.getByTestId("flag-reject-c2"));
    await user.click(screen.getByTestId("generate-redline-button"));
    expect(submitted).toEqual([
      { clause_id: "c1", decision: "approve" },
      { clause_id: "c2", decision: "reject" },
    ]);
  });

  // --- Controlled mode (onFlagDecision wiring) --------------------------

  it("controlled mode: each state change fires onFlagDecision", async () => {
    const user = userEvent.setup();
    const data = makeData([makeFlag({ clause_id: "c1" })]);
    const events: Array<{ clause_id: string; decision: string }> = [];
    render(
      <DeviationReviewPage
        {...RENDER_PROPS}
        data={data}
        onFlagDecision={(d) =>
          events.push({ clause_id: d.clause_id, decision: d.decision })
        }
      />,
    );
    await user.click(screen.getByTestId("flag-approve-c1"));
    expect(events).toEqual([{ clause_id: "c1", decision: "approve" }]);
    await user.click(screen.getByTestId("flag-add-context-c1"));
    const input = screen.getByTestId("flag-context-input-c1");
    await user.type(input, "ok");
    await user.click(screen.getByTestId("flag-save-context-c1"));
    expect(events).toContainEqual({
      clause_id: "c1",
      decision: "add_context",
    });
  });

  it("controlled mode: initialDecisions hydrates the row state on mount", () => {
    const data = makeData([makeFlag({ clause_id: "c1" })]);
    render(
      <DeviationReviewPage
        {...RENDER_PROPS}
        data={data}
        initialDecisions={[{ clause_id: "c1", decision: "approve" }]}
      />,
    );
    // The row's data-flag-action reflects the hydrated decision.
    expect(screen.getByTestId("deviation-row-c1")).toHaveAttribute(
      "data-flag-action",
      "approved",
    );
  });
});
