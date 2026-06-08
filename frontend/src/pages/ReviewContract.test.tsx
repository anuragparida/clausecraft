import { describe, it, expect, afterEach, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { withQueryClient } from "@/test/wrappers";
import { ReviewContractPage } from "@/pages/ReviewContract";

// ReviewContract — the connected wrapper around
// DeviationReview. Drives the spot call on mount, threads
// per-flag decisions up, and submits the batch on
// "Generate redline".

const originalFetch = globalThis.fetch;
beforeEach(() => {
  // Default fetch stub: the spot endpoint returns a small
  // flag list. Tests can override per-case.
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.includes("/contracts/spot")) {
      return new Response(
        JSON.stringify({
          filename: "demo.pdf",
          flag_count: 1,
          flagged_count: 1,
          unverified_count: 0,
          no_baseline_count: 0,
          matrix_version: "phase3",
          embedding_provider: "bge-m3",
          flags: [
            {
              clause_id: "c1",
              score: 2,
              rationale: "Term is 7y vs 3y baseline",
              citation: null,
              unverified: false,
              baseline_type: "term",
            },
          ],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    return new Response("{}", { status: 200 });
  }) as typeof fetch;
});
afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

const SAMPLE_CLAUSES = [
  {
    id: "c1",
    type: "term",
    text: "Term: 7 years.",
    language: "en",
    confidence: 0.9,
  },
];

describe("ReviewContractPage", () => {
  it("calls /contracts/spot on mount and renders the resulting row", async () => {
    render(
      withQueryClient(
        <ReviewContractPage
          contractId="demo-001"
          clauses={SAMPLE_CLAUSES}
          filename="demo.pdf"
          onBackToHome={() => {}}
          onViewAudit={() => {}}
          onRedlineReady={() => {}}
        />,
      ),
    );
    await waitFor(() => {
      expect(screen.getByTestId("deviation-row-c1")).toBeInTheDocument();
    });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/contracts/spot"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("the connected page keeps the user on the page while a flag is undecided", async () => {
    const onRedlineReady = vi.fn();
    render(
      withQueryClient(
        <ReviewContractPage
          contractId="demo-001"
          clauses={SAMPLE_CLAUSES}
          onBackToHome={() => {}}
          onViewAudit={() => {}}
          onRedlineReady={onRedlineReady}
        />,
      ),
    );
    await waitFor(() => {
      expect(screen.getByTestId("deviation-row-c1")).toBeInTheDocument();
    });
    const button = screen.getByTestId("generate-redline-button");
    expect(button).toBeDisabled();
    expect(onRedlineReady).not.toHaveBeenCalled();
  });

  it("approving all flags and clicking Generate redline calls onRedlineReady after the API call", async () => {
    const onRedlineReady = vi.fn();
    // The /decisions endpoint returns ok=true.
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockImplementation(
      async (input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/contracts/spot")) {
          return new Response(
            JSON.stringify({
              filename: "demo.pdf",
              flag_count: 1,
              flagged_count: 1,
              unverified_count: 0,
              no_baseline_count: 0,
              matrix_version: "phase3",
              embedding_provider: "bge-m3",
              flags: [
                {
                  clause_id: "c1",
                  score: 2,
                  rationale: "x",
                  citation: null,
                  unverified: false,
                  baseline_type: "term",
                },
              ],
            }),
            { status: 200, headers: { "content-type": "application/json" } },
          );
        }
        if (url.includes("/decisions")) {
          return new Response(JSON.stringify({ ok: true }), {
            status: 200,
            headers: { "content-type": "application/json" },
          });
        }
        return new Response("{}", { status: 200 });
      },
    );
    render(
      withQueryClient(
        <ReviewContractPage
          contractId="demo-001"
          clauses={SAMPLE_CLAUSES}
          onBackToHome={() => {}}
          onViewAudit={() => {}}
          onRedlineReady={onRedlineReady}
        />,
      ),
    );
    await waitFor(() => {
      expect(screen.getByTestId("deviation-row-c1")).toBeInTheDocument();
    });
    const user = userEvent.setup();
    await user.click(screen.getByTestId("flag-approve-c1"));
    await user.click(screen.getByTestId("generate-redline-button"));
    await waitFor(() => {
      expect(onRedlineReady).toHaveBeenCalledTimes(1);
    });
  });
});
