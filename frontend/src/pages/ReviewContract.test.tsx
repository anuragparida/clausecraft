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

  // --- F3 acceptance: refresh-after-pause UI hydration ----------
  //
  // The pipeline layer's state machine round-trips fine on
  // ``contract_id`` (see ``tests/pipeline/test_hitl_state_machine.py``).
  // The Phase 3 review flagged F3: the user-facing path was
  // broken because ReviewContractPage received no ``clauses``
  // prop from the hash router on a refresh. The fix is the
  // new ``GET /contracts/{id}/state`` endpoint and a
  // mount-time fetch in this page. The three tests below
  // exercise the UI re-mount path — the spec acceptance for
  // F3 — and lock the gap shut.
  describe("resume-after-pause UI hydration (F3)", () => {
    const FLAG_FOR_C1 = {
      clause_id: "c1",
      score: 2,
      rationale: "Term is 7y vs 3y baseline",
      citation: null,
      unverified: false,
      baseline_type: "term",
    };

    function mockStateEndpoint(opts: {
      has_state: boolean;
      has_ingest?: boolean;
      has_spot?: boolean;
      has_decisions?: boolean;
      has_redline?: boolean;
      flags?: Array<unknown>;
      decisions?: Array<unknown>;
    }) {
      (globalThis.fetch as ReturnType<typeof vi.fn>).mockImplementation(
        async (input: RequestInfo | URL) => {
          const url =
            typeof input === "string" ? input : input.toString();
          if (url.includes("/contracts/") && url.endsWith("/state")) {
            return new Response(
              JSON.stringify({
                contract_id: "demo-001",
                filename: "demo.pdf",
                has_state: opts.has_state,
                has_ingest: opts.has_ingest ?? false,
                has_spot: opts.has_spot ?? false,
                has_decisions: opts.has_decisions ?? false,
                has_redline: opts.has_redline ?? false,
                clauses: opts.has_ingest ? SAMPLE_CLAUSES : [],
                flags: opts.flags ?? [],
                decisions: opts.decisions ?? [],
                redlines: [],
              }),
              {
                status: 200,
                headers: { "content-type": "application/json" },
              },
            );
          }
          // If the spot endpoint is hit too, return a stub.
          if (url.includes("/contracts/spot")) {
            return new Response(
              JSON.stringify({
                filename: "demo.pdf",
                flag_count: 0,
                flagged_count: 0,
                unverified_count: 0,
                no_baseline_count: 0,
                matrix_version: "phase3",
                embedding_provider: "bge-m3",
                flags: [],
              }),
              { status: 200, headers: { "content-type": "application/json" } },
            );
          }
          return new Response("{}", { status: 200 });
        },
      );
    }

    it("fetches /state on mount when no clauses prop is passed", async () => {
      // The parent (App.tsx's hash router) does NOT pass
      // ``clauses`` when the user opens the URL cold. The
      // page must fetch /state itself to re-hydrate.
      mockStateEndpoint({ has_state: true, has_ingest: true });
      render(
        withQueryClient(
          <ReviewContractPage
            contractId="demo-001"
            onBackToHome={() => {}}
            onViewAudit={() => {}}
            onRedlineReady={() => {}}
          />,
        ),
      );
      await waitFor(() => {
        expect(globalThis.fetch).toHaveBeenCalledWith(
          expect.stringMatching(/\/api\/contracts\/demo-001\/state/),
          expect.anything(),
        );
      });
    });

    it("hydrates the spot flags from server state without re-spotting", async () => {
      // After a refresh mid-review, the server already
      // has spot flags stashed. The page must use them
      // directly — re-running the spotter would change
      // the flag set and silently lose the user's prior
      // decisions.
      mockStateEndpoint({
        has_state: true,
        has_ingest: true,
        has_spot: true,
        has_decisions: true,
        flags: [FLAG_FOR_C1],
        decisions: [{ clause_id: "c1", action: "accepted" }],
      });
      render(
        withQueryClient(
          <ReviewContractPage
            contractId="demo-001"
            onBackToHome={() => {}}
            onViewAudit={() => {}}
            onRedlineReady={() => {}}
          />,
        ),
      );
      // The row appears without a /spot call — flags
      // came from the state endpoint.
      await waitFor(() => {
        expect(screen.getByTestId("deviation-row-c1")).toBeInTheDocument();
      });
      // The page must NOT have called /spot (no
      // re-spotting after refresh).
      const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
      const spotCalls = fetchMock.mock.calls.filter(
        (call) => typeof call[0] === "string" && call[0].includes("/contracts/spot"),
      );
      expect(spotCalls).toHaveLength(0);
    });

    it("hydrates prior decisions and lets the user generate the redline", async () => {
      // The user had approved c1 before the refresh;
      // the page must restore that approval so the
      // "Generate redline" button is enabled.
      mockStateEndpoint({
        has_state: true,
        has_ingest: true,
        has_spot: true,
        has_decisions: true,
        flags: [FLAG_FOR_C1],
        decisions: [{ clause_id: "c1", action: "accepted" }],
      });
      const onRedlineReady = vi.fn();
      // Override the /decisions response. We use
      // ``mockImplementationOnce`` chained inside the
      // main impl so the state fetch is unaffected.
      const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
      const baseImpl = fetchMock.getMockImplementation();
      fetchMock.mockImplementation(
        async (input: RequestInfo | URL) => {
          const url =
            typeof input === "string" ? input : input.toString();
          if (url.includes("/decisions")) {
            return new Response(JSON.stringify({ ok: true }), {
              status: 200,
              headers: { "content-type": "application/json" },
            });
          }
          if (baseImpl) return baseImpl(input);
          return new Response("{}", { status: 200 });
        },
      );
      render(
        withQueryClient(
          <ReviewContractPage
            contractId="demo-001"
            onBackToHome={() => {}}
            onViewAudit={() => {}}
            onRedlineReady={onRedlineReady}
          />,
        ),
      );
      await waitFor(() => {
        expect(screen.getByTestId("deviation-row-c1")).toBeInTheDocument();
      });
      // The approve button is in the "approved" state
      // because the page hydrated the prior decision.
      // The "Generate redline" button is enabled
      // (the user's previous approve carries over).
      const button = screen.getByTestId("generate-redline-button");
      await waitFor(() => {
        expect(button).not.toBeDisabled();
      });
      const user = userEvent.setup();
      await user.click(button);
      await waitFor(() => {
        expect(onRedlineReady).toHaveBeenCalledTimes(1);
      });
    });

    it("renders a friendly 'contract not found' state for an unknown contract", async () => {
      // Refresh an unknown URL → 200 with has_state=false.
      // The page must render a friendly empty state
      // instead of a blank page (the F3 acceptance test
      // from the card body: a stale URL is the F3 case).
      mockStateEndpoint({ has_state: false });
      render(
        withQueryClient(
          <ReviewContractPage
            contractId="ghost-001"
            onBackToHome={() => {}}
            onViewAudit={() => {}}
            onRedlineReady={() => {}}
          />,
        ),
      );
      await waitFor(() => {
        expect(
          screen.getByTestId("review-contract-empty"),
        ).toBeInTheDocument();
      });
      expect(screen.getByText(/Contract not found/i)).toBeInTheDocument();
    });
  });
});
