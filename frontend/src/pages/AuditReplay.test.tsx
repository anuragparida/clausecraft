import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { withQueryClient } from "@/test/wrappers";
import { AuditReplayPage } from "@/pages/AuditReplay";

// AuditReplay: fetch the audit log on mount, render the
// timeline, drive the JSON/PDF download buttons. We mock
// the global ``fetch`` for the audit-log endpoint and the
// blob download.

const originalFetch = globalThis.fetch;
const originalCreateObjectURL = URL.createObjectURL;
const originalRevokeObjectURL = URL.revokeObjectURL;

beforeEach(() => {
  // Stub URL.createObjectURL so the download helper
  // doesn't crash in jsdom (it has no Blob URL support).
  URL.createObjectURL = vi.fn(() => "blob:mock") as typeof URL.createObjectURL;
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  URL.createObjectURL = originalCreateObjectURL;
  URL.revokeObjectURL = originalRevokeObjectURL;
  vi.restoreAllMocks();
});

describe("AuditReplayPage", () => {
  it("renders the loading state on first mount", () => {
    globalThis.fetch = vi.fn(
      () =>
        new Promise<Response>(() => {
          /* never resolves */
        }),
    ) as typeof fetch;
    render(
      withQueryClient(
        <AuditReplayPage
          contractId="demo-001"
          onBackToHome={() => {}}
        />,
      ),
    );
    expect(screen.getByTestId("audit-loading")).toBeInTheDocument();
  });

  it("renders the timeline rows on a successful fetch", async () => {
    const rows = [
      {
        contract_id: "demo-001",
        clause_id: "c1",
        decision_type: "flag_accepted",
        payload_json: {},
        decided_by: "operator-1",
        decided_at: "2026-06-08T14:32:08.000Z",
      },
      {
        contract_id: "demo-001",
        clause_id: "",
        decision_type: "graph_started",
        payload_json: { clause_count: 7 },
        decided_by: "operator-1",
        decided_at: "2026-06-08T14:31:42.000Z",
      },
    ];
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify(rows), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as typeof fetch;

    render(
      withQueryClient(
        <AuditReplayPage contractId="demo-001" onBackToHome={() => {}} />,
      ),
    );

    await waitFor(() => {
      expect(
        screen.queryByTestId("audit-timeline"),
      ).toBeInTheDocument();
    });
    // The fetch was called with the right URL (the
    // Vite-dev-proxy strips /api in production; we
    // only check the suffix here).
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/contracts/demo-001/audit-log.json"),
    );
  });

  it("renders the error state on a failed fetch", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ detail: "not found" }), {
        status: 404,
        headers: { "content-type": "application/json" },
      }),
    ) as typeof fetch;

    render(
      withQueryClient(
        <AuditReplayPage contractId="demo-001" onBackToHome={() => {}} />,
      ),
    );

    await waitFor(() => {
      expect(screen.getByTestId("audit-error")).toBeInTheDocument();
    });
  });

  it("Download JSON button is disabled when there are no rows", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as typeof fetch;

    render(
      withQueryClient(
        <AuditReplayPage contractId="demo-001" onBackToHome={() => {}} />,
      ),
    );
    await waitFor(() => {
      expect(
        screen.getByTestId("audit-download-json"),
      ).toBeInTheDocument();
    });
    expect(screen.getByTestId("audit-download-json")).toBeDisabled();
  });

  it("renders a timeline scrubber for rows that span a timestamp range", async () => {
    const rows = [
      {
        contract_id: "demo-001",
        clause_id: "c1",
        decision_type: "flag_accepted",
        payload_json: { note: "oldest" },
        decided_by: "operator-1",
        decided_at: "2026-06-08T14:31:42.000Z",
      },
      {
        contract_id: "demo-001",
        clause_id: "c2",
        decision_type: "severity_edited",
        payload_json: { old_severity: 2, new_severity: 1 },
        decided_by: "operator-1",
        decided_at: "2026-06-08T14:32:08.000Z",
      },
      {
        contract_id: "demo-001",
        clause_id: "",
        decision_type: "redline_generated",
        payload_json: { accepted_count: 1 },
        decided_by: "operator-1",
        decided_at: "2026-06-08T14:35:00.000Z",
      },
    ];
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify(rows), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as typeof fetch;

    render(
      withQueryClient(
        <AuditReplayPage contractId="demo-001" onBackToHome={() => {}} />,
      ),
    );

    // The scrubber appears once the rows have loaded.
    const slider = await screen.findByTestId("audit-scrub-slider");
    expect(slider).toBeInTheDocument();

    // All 3 rows visible by default.
    const initialRows = screen.getAllByTestId("audit-timeline-row");
    expect(initialRows.length).toBe(3);
  });

  it("scrubber filters the visible rows when dragged left", async () => {
    const rows = [
      {
        contract_id: "demo-001",
        clause_id: "c1",
        decision_type: "flag_accepted",
        payload_json: { note: "oldest" },
        decided_by: "operator-1",
        decided_at: "2026-06-08T14:31:42.000Z",
      },
      {
        contract_id: "demo-001",
        clause_id: "c2",
        decision_type: "severity_edited",
        payload_json: { old_severity: 2, new_severity: 1 },
        decided_by: "operator-1",
        decided_at: "2026-06-08T14:32:08.000Z",
      },
      {
        contract_id: "demo-001",
        clause_id: "",
        decision_type: "redline_generated",
        payload_json: { accepted_count: 1 },
        decided_by: "operator-1",
        decided_at: "2026-06-08T14:35:00.000Z",
      },
    ];
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify(rows), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as typeof fetch;

    render(
      withQueryClient(
        <AuditReplayPage contractId="demo-001" onBackToHome={() => {}} />,
      ),
    );
    const slider = await screen.findByTestId("audit-scrub-slider") as HTMLInputElement;
    // Drag the slider to a point between the oldest and
    // middle row — exactly the oldest row remains visible.
    const oldest = Date.parse("2026-06-08T14:31:42.000Z");
    const middle = Date.parse("2026-06-08T14:32:08.000Z");
    fireEvent.change(slider, {
      target: { value: String(Math.floor((oldest + middle) / 2)) },
    });
    const visibleRows = screen.getAllByTestId("audit-timeline-row");
    expect(visibleRows.length).toBe(1);
    expect(visibleRows[0]).toHaveAttribute(
      "data-decision-type",
      "flag_accepted",
    );
    // Sanity: the reset button is enabled (we dragged).
    expect(screen.getByTestId("audit-scrub-reset")).not.toBeDisabled();
  });

  it("clicking a row disclosure expands the payload_json", async () => {
    const rows = [
      {
        contract_id: "demo-001",
        clause_id: "c1",
        decision_type: "flag_accepted",
        payload_json: { note: "click me", extra: 42 },
        decided_by: "operator-1",
        decided_at: "2026-06-08T14:31:42.000Z",
      },
      {
        contract_id: "demo-001",
        clause_id: "c2",
        decision_type: "severity_edited",
        payload_json: { old_severity: 2, new_severity: 1 },
        decided_by: "operator-1",
        decided_at: "2026-06-08T14:32:08.000Z",
      },
    ];
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify(rows), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as typeof fetch;

    const user = userEvent.setup();
    render(
      withQueryClient(
        <AuditReplayPage contractId="demo-001" onBackToHome={() => {}} />,
      ),
    );
    // Wait for the rows to render.
    await screen.findByTestId("audit-scrub-slider");
    const toggle = await screen.findByTestId("audit-row-toggle-0");
    // Closed: no payload element yet.
    expect(screen.queryByTestId("audit-row-payload-0")).toBeNull();
    await user.click(toggle);
    // Open: the pretty-printed JSON is in the DOM.
    const payload = await screen.findByTestId("audit-row-payload-0");
    expect(payload).toHaveTextContent("click me");
    expect(payload).toHaveTextContent("42");
  });
});

// --- Phase 6: event markers above the scrubber --------------------------

/** Three rows spanning a real timestamp range so the
 *  scrubber + markers both render. */
function threeRowFixture() {
  return [
    {
      contract_id: "demo-001",
      clause_id: "c1",
      decision_type: "flag_accepted",
      payload_json: {},
      decided_by: "operator-1",
      decided_at: "2026-06-08T14:31:42.000Z",
    },
    {
      contract_id: "demo-001",
      clause_id: "c2",
      decision_type: "severity_edited",
      payload_json: { old_severity: 2, new_severity: 1 },
      decided_by: "operator-1",
      decided_at: "2026-06-08T14:32:08.000Z",
    },
    {
      contract_id: "demo-001",
      clause_id: "",
      decision_type: "redline_generated",
      payload_json: { accepted_count: 1 },
      decided_by: "operator-1",
      decided_at: "2026-06-08T14:35:00.000Z",
    },
  ];
}

describe("AuditReplayPage — Phase 6 event markers above the scrubber", () => {
  it("renders one marker per visible row when scrubbing is enabled", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify(threeRowFixture()), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as typeof fetch;

    render(
      withQueryClient(
        <AuditReplayPage contractId="demo-001" onBackToHome={() => {}} />,
      ),
    );

    // Slider exists → markers should too (canScrub is
    // true: 3 events span 14:31:42 → 14:35:00).
    await screen.findByTestId("audit-scrub-slider");
    expect(screen.getByTestId("audit-event-axis")).toBeInTheDocument();
    // 3 markers, indexed 0..2, ordered chronologically.
    expect(screen.getByTestId("audit-event-marker-0")).toBeInTheDocument();
    expect(screen.getByTestId("audit-event-marker-1")).toBeInTheDocument();
    expect(screen.getByTestId("audit-event-marker-2")).toBeInTheDocument();
  });

  it("does NOT render markers when there is a single event (canScrub=false)", async () => {
    // Single-row response — canScrub is false (maxMs ==
    // minMs), so the slider + markers are both hidden.
    const oneRow = [threeRowFixture()[0]];
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify(oneRow), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as typeof fetch;

    render(
      withQueryClient(
        <AuditReplayPage contractId="demo-001" onBackToHome={() => {}} />,
      ),
    );

    // Wait for the row to render.
    await screen.findByTestId("audit-timeline-row");
    // No slider, no axis, no markers.
    expect(screen.queryByTestId("audit-scrub-slider")).toBeNull();
    expect(screen.queryByTestId("audit-event-axis")).toBeNull();
    expect(screen.queryByTestId("audit-event-marker-0")).toBeNull();
  });

  it("positions markers proportionally within [minMs, maxMs]", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify(threeRowFixture()), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as typeof fetch;

    render(
      withQueryClient(
        <AuditReplayPage contractId="demo-001" onBackToHome={() => {}} />,
      ),
    );
    await screen.findByTestId("audit-event-marker-2");

    // Compute expected percentages from the fixture's
    // timestamps.
    const lo = Date.parse("2026-06-08T14:31:42.000Z");
    const mid = Date.parse("2026-06-08T14:32:08.000Z");
    const hi = Date.parse("2026-06-08T14:35:00.000Z");
    const span = hi - lo;

    // Markers are ordered chronologically (sorted by ts).
    // We compare numerically (parsing the inline ``left``
    // style) to avoid floating-point string format
    // differences between our expected math and the
    // browser's serialisation.
    const expectedLeft = (t: number) => `${((t - lo) / span) * 100}%`;
    const actualLeftPct = (el: HTMLElement) =>
      Number.parseFloat(el.style.left);
    const expectedLeftPct = (t: number) => ((t - lo) / span) * 100;

    const m0 = screen.getByTestId("audit-event-marker-0");
    const m1 = screen.getByTestId("audit-event-marker-1");
    const m2 = screen.getByTestId("audit-event-marker-2");

    // Sanity: the inline ``left`` style is a percentage
    // string of the form "N%".
    expect(m0.style.left).toMatch(/^[0-9.]+%/);
    expect(expectedLeft(lo)).toBe("0%");
    expect(expectedLeft(hi)).toBe("100%");
    // Numerical comparison — tolerant of float format.
    expect(actualLeftPct(m0)).toBeCloseTo(expectedLeftPct(lo), 6);
    expect(actualLeftPct(m1)).toBeCloseTo(expectedLeftPct(mid), 6);
    expect(actualLeftPct(m2)).toBeCloseTo(expectedLeftPct(hi), 6);
  });

  it("each marker carries a title tooltip with decision type + relative time", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify(threeRowFixture()), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as typeof fetch;

    render(
      withQueryClient(
        <AuditReplayPage contractId="demo-001" onBackToHome={() => {}} />,
      ),
    );
    const m2 = await screen.findByTestId("audit-event-marker-2");
    // Most recent row → "0s ago" relative to itself.
    expect(m2.getAttribute("title")).toMatch(/Redline generated/);
    expect(m2.getAttribute("title")).toMatch(/0s ago/);

    // Oldest row → some non-zero "X ago" string.
    const m0 = screen.getByTestId("audit-event-marker-0");
    expect(m0.getAttribute("title")).toMatch(/Flag accepted/);
    expect(m0.getAttribute("title")).toMatch(/ago/);
  });

  it("clicking a marker moves the scrubber to that timestamp", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify(threeRowFixture()), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as typeof fetch;

    const user = userEvent.setup();
    render(
      withQueryClient(
        <AuditReplayPage contractId="demo-001" onBackToHome={() => {}} />,
      ),
    );
    const slider = (await screen.findByTestId(
      "audit-scrub-slider",
    )) as HTMLInputElement;
    const marker = await screen.findByTestId("audit-event-marker-0");

    // Sanity: slider starts at maxMs (newest event).
    const hi = Date.parse("2026-06-08T14:35:00.000Z");
    expect(slider.value).toBe(String(hi));

    // Click the oldest marker.
    await user.click(marker);
    // Slider moves to that timestamp.
    const lo = Date.parse("2026-06-08T14:31:42.000Z");
    expect(slider.value).toBe(String(lo));
    // Reset button is now enabled (we moved it).
    expect(screen.getByTestId("audit-scrub-reset")).not.toBeDisabled();
  });

  it("markers inherit the decision-type tone colors", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify(threeRowFixture()), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as typeof fetch;

    render(
      withQueryClient(
        <AuditReplayPage contractId="demo-001" onBackToHome={() => {}} />,
      ),
    );
    const m0 = await screen.findByTestId("audit-event-marker-0");
    const m1 = await screen.findByTestId("audit-event-marker-1");
    const m2 = await screen.findByTestId("audit-event-marker-2");
    // flag_accepted → emerald-500.
    expect(m0.className).toContain("bg-emerald-500");
    // severity_edited → amber-500.
    expect(m1.className).toContain("bg-amber-500");
    // redline_generated → slate-400.
    expect(m2.className).toContain("bg-slate-400");
  });
});
