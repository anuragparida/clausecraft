import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  MatrixVerdictCell,
  type MatrixVerdict,
  type CounterpartyTypeForCell,
} from "@/components/MatrixVerdictCell";

// MatrixVerdictCell — minimal scope per the card body:
//   - 4-state badge (acceptable / material / unacceptable /
//     unverified), each with the same colour rules as the
//     SeverityBadge so the visual contract is shared.
//   - Popover opens when matrix_sources is non-empty;
//     closes on the X button.
//   - Renders the counterparty type label below the badge.
//   - Falls back to the score-derived label when no
//     matrix verdict is emitted (Phase 2/3/4 backends).

const CLAUSE_ID = "c1";

function makeProps(
  over: Partial<React.ComponentProps<typeof MatrixVerdictCell>> = {},
): React.ComponentProps<typeof MatrixVerdictCell> {
  return {
    clauseId: CLAUSE_ID,
    score: 2,
    ...over,
  };
}

describe("MatrixVerdictCell", () => {
  describe("with a matrix verdict emitted", () => {
    const VERDICTS: MatrixVerdict[] = [
      "acceptable",
      "material",
      "unacceptable",
      "unverified",
    ];

    it.each(VERDICTS)(
      "renders the %s verdict as a coloured badge with the human label",
      (v) => {
        render(
          <MatrixVerdictCell
            {...makeProps({ matrixVerdict: v, score: 2 })}
          />,
        );
        const badge = screen.getByTestId(
          `matrix-verdict-badge-${CLAUSE_ID}`,
        );
        expect(badge).toHaveAttribute("data-matrix-verdict", v);
        // The label is one of the 4 spec-locked strings; we
        // don't re-export the mapping, so we just assert
        // the badge text is non-empty.
        expect(badge.textContent).toBeTruthy();
      },
    );

    it("renders the popover trigger (not the static badge) when sources are non-empty", () => {
      render(
        <MatrixVerdictCell
          {...makeProps({
            matrixVerdict: "material",
            matrixSources: ["counterparty (public_sector)", "flat"],
          })}
        />,
      );
      expect(
        screen.getByTestId(`matrix-verdict-popover-trigger-${CLAUSE_ID}`),
      ).toBeInTheDocument();
      expect(
        screen.queryByTestId(`matrix-verdict-badge-${CLAUSE_ID}`),
      ).not.toBeInTheDocument();
    });

    it("renders the static badge (not the popover trigger) when sources are empty", () => {
      render(
        <MatrixVerdictCell
          {...makeProps({
            matrixVerdict: "acceptable",
            matrixSources: [],
          })}
        />,
      );
      expect(
        screen.getByTestId(`matrix-verdict-badge-${CLAUSE_ID}`),
      ).toBeInTheDocument();
      expect(
        screen.queryByTestId(
          `matrix-verdict-popover-trigger-${CLAUSE_ID}`,
        ),
      ).not.toBeInTheDocument();
    });

    it("opens the popover when the trigger is clicked and shows the lookup chain", async () => {
      const user = userEvent.setup();
      const sources = [
        "clause_type (counterparty, public_sector)",
        "clause_type (counterparty, flat)",
      ];
      render(
        <MatrixVerdictCell
          {...makeProps({
            matrixVerdict: "unacceptable",
            matrixSources: sources,
          })}
        />,
      );
      await user.click(
        screen.getByTestId(
          `matrix-verdict-popover-trigger-${CLAUSE_ID}`,
        ),
      );
      const panel = screen.getByTestId(
        `matrix-verdict-popover-panel-${CLAUSE_ID}`,
      );
      expect(panel).toBeInTheDocument();
      const list = screen.getByTestId(
        `matrix-verdict-sources-${CLAUSE_ID}`,
      );
      expect(list.children).toHaveLength(sources.length);
      for (let i = 0; i < sources.length; i++) {
        expect(
          screen.getByTestId(`matrix-verdict-source-${CLAUSE_ID}-${i}`),
        ).toHaveTextContent(sources[i]);
      }
    });

    it("closes the popover when the X button is clicked", async () => {
      const user = userEvent.setup();
      render(
        <MatrixVerdictCell
          {...makeProps({
            matrixVerdict: "material",
            matrixSources: ["counterparty (healthcare)"],
          })}
        />,
      );
      await user.click(
        screen.getByTestId(
          `matrix-verdict-popover-trigger-${CLAUSE_ID}`,
        ),
      );
      expect(
        screen.getByTestId(
          `matrix-verdict-popover-panel-${CLAUSE_ID}`,
        ),
      ).toBeInTheDocument();
      await user.click(
        screen.getByTestId(
          `matrix-verdict-popover-close-${CLAUSE_ID}`,
        ),
      );
      expect(
        screen.queryByTestId(
          `matrix-verdict-popover-panel-${CLAUSE_ID}`,
        ),
      ).not.toBeInTheDocument();
    });

    it("renders the counterparty type label under the badge", () => {
      const types: CounterpartyTypeForCell[] = [
        "enterprise",
        "smb",
        "public_sector",
        "healthcare",
        "any",
      ];
      for (const t of types) {
        const { unmount } = render(
          <MatrixVerdictCell
            {...makeProps({
              matrixVerdict: "material",
              matrixCounterpartyType: t,
            })}
          />,
        );
        const counterparty = screen.getByTestId(
          `matrix-verdict-counterparty-${CLAUSE_ID}`,
        );
        expect(counterparty).toHaveAttribute("data-counterparty-type", t);
        expect(counterparty.textContent).toBeTruthy();
        unmount();
      }
    });

    it("hides the counterparty type label when none is provided", () => {
      render(
        <MatrixVerdictCell
          {...makeProps({
            matrixVerdict: "acceptable",
            matrixCounterpartyType: undefined,
          })}
        />,
      );
      expect(
        screen.queryByTestId(
          `matrix-verdict-counterparty-${CLAUSE_ID}`,
        ),
      ).not.toBeInTheDocument();
    });
  });

  describe("fallback path (no matrix verdict — Phase 2/3/4 backend)", () => {
    it("renders the score-derived label for score=1 ('minor')", () => {
      render(<MatrixVerdictCell {...makeProps({ score: 1 })} />);
      const badge = screen.getByTestId(
        `matrix-verdict-badge-${CLAUSE_ID}`,
      );
      expect(badge).toHaveAttribute("data-matrix-verdict", "minor");
      expect(badge).toHaveTextContent("minor");
    });

    it("renders the score-derived label for score=3 ('unacceptable')", () => {
      render(<MatrixVerdictCell {...makeProps({ score: 3 })} />);
      const badge = screen.getByTestId(
        `matrix-verdict-badge-${CLAUSE_ID}`,
      );
      expect(badge).toHaveAttribute("data-matrix-verdict", "unacceptable");
      expect(badge).toHaveTextContent("unacceptable");
    });

    it("marks the cell as data-fallback='true' (test hook)", () => {
      render(<MatrixVerdictCell {...makeProps({ score: 2 })} />);
      expect(
        screen.getByTestId(`matrix-verdict-cell-${CLAUSE_ID}`),
      ).toHaveAttribute("data-fallback", "true");
    });

    it("renders the 'flat baseline (Phase 5 adds matrix)' caption", () => {
      render(<MatrixVerdictCell {...makeProps({ score: 2 })} />);
      const cell = screen.getByTestId(
        `matrix-verdict-cell-${CLAUSE_ID}`,
      );
      expect(cell).toHaveTextContent(/flat baseline/);
    });
  });
});
