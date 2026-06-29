import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { RecentContractsCard } from "@/components/RecentContractsCard";
import type { ContractSummary } from "@/lib/api";

// RecentContractsCard — Phase 6 home grid card.
//
// Three states the card has to handle cleanly:
//
// 1. **Loading.** The fetch is in-flight; render a
//    placeholder row.
// 2. **Ready.** The list arrived; render one row per
//    contract with a "pipeline stage · relative time"
//    summary, and an "Open review" button on the right.
// 3. **Error.** The fetch rejected; render the error
//    inline.
//
// Plus a click-handler test: clicking a row should call
// the ``onOpenContract`` prop with the contract's id, so
// the App-level router can navigate to the review page.
//
// The test mocks ``globalThis.fetch`` directly (the same
// pattern TriagePage.test.tsx and RedlineOutput.test.tsx
// use), since ``api.ts`` is a thin wrapper around
// ``fetch``.

interface RecentContractsFixture {
  rows: ContractSummary[];
  fetchImpl?: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
}

function makeRecentContractsFixture({
  rows,
  fetchImpl,
}: RecentContractsFixture): ContractSummary[] {
  // Mock ``globalThis.fetch`` to return the rows.
  const fetchMock = vi.fn(
    fetchImpl ??
      (async () =>
        new Response(JSON.stringify(rows), {
          status: 200,
          headers: { "content-type": "application/json" },
        })),
  );
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  return rows;
}

function isoMinutesAgo(minutes: number): string {
  return new Date(Date.now() - minutes * 60 * 1000).toISOString();
}

afterEach(() => {
  // Reset the global fetch between tests so one test's
  // mock doesn't leak into the next.
  vi.restoreAllMocks();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  delete (globalThis as any).fetch;
});

// --- Loading + empty / error states -----------------------------------

describe("RecentContractsCard — load lifecycle", () => {
  it("renders the loading placeholder while the fetch is in flight", () => {
    // A fetch that never resolves — exercises the
    // loading branch without a flushMicrotasks dance.
    globalThis.fetch = vi.fn(
      () => new Promise<Response>(() => {}),
    ) as unknown as typeof fetch;

    render(<RecentContractsCard onOpenContract={() => {}} />);
    expect(screen.getByTestId("home-recent-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("home-recent-empty")).not.toBeInTheDocument();
    expect(screen.queryByTestId("home-recent-error")).not.toBeInTheDocument();
  });

  it("renders the empty state when the backend returns []", async () => {
    makeRecentContractsFixture({ rows: [] });
    render(<RecentContractsCard onOpenContract={() => {}} />);

    const empty = await screen.findByTestId("home-recent-empty");
    expect(empty).toHaveTextContent(/no contracts yet/i);
    expect(screen.queryByTestId("home-recent-list")).not.toBeInTheDocument();
  });

  it("renders an inline error message when the fetch rejects", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("network down");
    }) as unknown as typeof fetch;

    render(<RecentContractsCard onOpenContract={() => {}} />);

    const err = await screen.findByTestId("home-recent-error");
    expect(err).toHaveAttribute("role", "alert");
    expect(err).toHaveTextContent(/network down/);
  });

  it("renders an inline ApiError message when the backend 5xx's", async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "boom" }), {
          status: 500,
          headers: { "content-type": "application/json" },
        }),
    ) as unknown as typeof fetch;

    render(<RecentContractsCard onOpenContract={() => {}} />);

    const err = await screen.findByTestId("home-recent-error");
    expect(err).toHaveTextContent(/500/);
  });
});

// --- Ready state rendering --------------------------------------------

describe("RecentContractsCard — ready state rendering", () => {
  const baseRow: ContractSummary = {
    contract_id: "nda-001.pdf",
    filename: "nda-001.pdf",
    has_ingest: true,
    has_spot: true,
    has_decisions: false,
    has_redline: false,
    clause_count: 8,
    flag_count: 2,
    decision_count: 0,
    last_touched_at: isoMinutesAgo(3),
  };

  it("renders one list item per contract returned by the API", async () => {
    makeRecentContractsFixture({
      rows: [
        baseRow,
        {
          ...baseRow,
          contract_id: "nda-002.pdf",
          filename: "nda-002.pdf",
          has_decisions: true,
          decision_count: 5,
          flag_count: 5,
          last_touched_at: isoMinutesAgo(60),
        },
      ],
    });
    render(<RecentContractsCard onOpenContract={() => {}} />);

    await screen.findByTestId("home-recent-list");
    const rows = screen.getAllByTestId("home-recent-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveAttribute("data-contract-id", "nda-001.pdf");
    expect(rows[1]).toHaveAttribute("data-contract-id", "nda-002.pdf");
  });

  it("shows the contract filename as the primary row label", async () => {
    makeRecentContractsFixture({
      rows: [{ ...baseRow, filename: "My Vendor MSA.pdf" }],
    });
    render(<RecentContractsCard onOpenContract={() => {}} />);

    await screen.findByTestId("home-recent-list");
    expect(screen.getByText("My Vendor MSA.pdf")).toBeInTheDocument();
  });

  it("renders the most-advanced pipeline stage as the row badge", async () => {
    makeRecentContractsFixture({
      rows: [
        { ...baseRow, contract_id: "ingested.pdf" }, // Spotted
        {
          ...baseRow,
          contract_id: "decided.pdf",
          has_decisions: true,
          decision_count: 3,
          flag_count: 3,
        }, // Decisions in
        {
          ...baseRow,
          contract_id: "redlined.pdf",
          has_decisions: true,
          has_redline: true,
          decision_count: 3,
          flag_count: 3,
        }, // Redline ready
      ],
    });
    render(<RecentContractsCard onOpenContract={() => {}} />);

    await screen.findByTestId("home-recent-list");
    // Each row's button carries the stage label in its
    // secondary text. Scope to the first row's data-testid
    // so the assertion is unambiguous about *which* row.
    const firstRow = screen.getAllByTestId("home-recent-row")[0];
    expect(firstRow).toHaveTextContent(/Spotted/);
    expect(firstRow).toHaveTextContent(/3 min ago/);
    // The two later stages appear in later rows.
    const allRows = screen.getAllByTestId("home-recent-row");
    expect(allRows[1]).toHaveTextContent(/Decisions in/);
    expect(allRows[2]).toHaveTextContent(/Redline ready/);
  });

  it("shows the flag count when the contract has been spotted", async () => {
    makeRecentContractsFixture({
      rows: [
        { ...baseRow, flag_count: 1 },
        { ...baseRow, contract_id: "nda-002.pdf", flag_count: 3 },
      ],
    });
    render(<RecentContractsCard onOpenContract={() => {}} />);

    await screen.findByTestId("home-recent-list");
    // 1 flag → "1 flag" (no plural).
    expect(screen.getAllByText(/1 flag\b/)[0]).toBeInTheDocument();
    // 3 flags → "3 flags".
    expect(screen.getAllByText(/3 flags/)[0]).toBeInTheDocument();
  });
});

// --- Click handler -----------------------------------------------------

describe("RecentContractsCard — click handling", () => {
  const sampleRow: ContractSummary = {
    contract_id: "nda-001.pdf",
    filename: "nda-001.pdf",
    has_ingest: true,
    has_spot: true,
    has_decisions: false,
    has_redline: false,
    clause_count: 8,
    flag_count: 2,
    decision_count: 0,
    last_touched_at: new Date().toISOString(),
  };

  it("calls onOpenContract with the row's contract_id when the row body is clicked", async () => {
    const user = userEvent.setup();
    makeRecentContractsFixture({ rows: [sampleRow] });
    const onOpen = vi.fn();
    render(<RecentContractsCard onOpenContract={onOpen} />);

    await screen.findByTestId("home-recent-list");
    await user.click(screen.getByTestId("home-recent-row-button"));
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(onOpen).toHaveBeenCalledWith("nda-001.pdf");
  });

  it("calls onOpenContract when the 'Open review' button is clicked", async () => {
    const user = userEvent.setup();
    makeRecentContractsFixture({ rows: [sampleRow] });
    const onOpen = vi.fn();
    render(<RecentContractsCard onOpenContract={onOpen} />);

    await screen.findByTestId("home-recent-list");
    await user.click(screen.getByTestId("home-recent-row-open"));
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(onOpen).toHaveBeenCalledWith("nda-001.pdf");
  });
});

// --- Network call shape ------------------------------------------------

describe("RecentContractsCard — network call", () => {
  it("fetches /api/contracts with the default limit on mount", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    render(<RecentContractsCard onOpenContract={() => {}} />);

    await screen.findByTestId("home-recent-empty");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const firstCall = fetchMock.mock.calls[0] as unknown as [string];
    expect(firstCall[0]).toMatch(/^\/api\/contracts\?limit=10$/);
  });
});