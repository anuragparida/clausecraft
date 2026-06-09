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
