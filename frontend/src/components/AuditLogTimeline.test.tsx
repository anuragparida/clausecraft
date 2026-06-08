import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { AuditLogTimeline } from "@/components/AuditLogTimeline";
import type { AuditLogRow } from "@/lib/api";

// AuditLogTimeline: empty state, row rendering in
// chronological order, payload summary text, decision-type
// color dots, and the timestamp/actor layout.

function makeRow(over: Partial<AuditLogRow> = {}): AuditLogRow {
  return {
    contract_id: "demo-001",
    clause_id: "c1",
    decision_type: "flag_accepted",
    payload_json: {},
    decided_by: "operator-1",
    decided_at: "2026-06-08T14:32:08.000Z",
    ...over,
  };
}

describe("AuditLogTimeline", () => {
  it("renders the empty state when rows=[]", () => {
    render(<AuditLogTimeline rows={[]} />);
    expect(screen.getByTestId("audit-timeline-empty")).toBeInTheDocument();
  });

  it("renders one row per AuditLogRow in chronological order", () => {
    const rows: AuditLogRow[] = [
      makeRow({
        decision_type: "redline_downloaded",
        decided_at: "2026-06-08T14:35:00.000Z",
        payload_json: {},
      }),
      makeRow({
        decision_type: "flag_accepted",
        decided_at: "2026-06-08T14:32:08.000Z",
        clause_id: "c1",
      }),
      makeRow({
        decision_type: "graph_started",
        decided_at: "2026-06-08T14:31:42.000Z",
        clause_id: "",
        payload_json: { clause_count: 7 },
      }),
    ];
    render(<AuditLogTimeline rows={rows} />);
    const list = screen.getByTestId("audit-timeline");
    const listRows = within(list).getAllByTestId("audit-timeline-row");
    expect(listRows).toHaveLength(3);
    // First row: graph_started (oldest).
    expect(listRows[0]).toHaveAttribute("data-decision-type", "graph_started");
    // Last row: redline_downloaded (newest).
    expect(listRows[2]).toHaveAttribute(
      "data-decision-type",
      "redline_downloaded",
    );
  });

  it("renders a human-friendly decision type label", () => {
    render(
      <AuditLogTimeline
        rows={[makeRow({ decision_type: "flag_accepted", clause_id: "c1" })]}
      />,
    );
    expect(
      screen.getByTestId("audit-timeline-decision-type"),
    ).toHaveTextContent("Flag accepted");
  });

  it("renders a payload summary that includes the clause id for flag events", () => {
    render(
      <AuditLogTimeline
        rows={[makeRow({ decision_type: "flag_accepted", clause_id: "c4" })]}
      />,
    );
    expect(screen.getByTestId("audit-timeline-summary")).toHaveTextContent(
      "clause c4",
    );
  });

  it("renders the actor (decided_by) in the timestamp line", () => {
    render(
      <AuditLogTimeline
        rows={[makeRow({ decided_by: "operator-7" })]}
      />,
    );
    expect(screen.getByTestId("audit-timeline-actor")).toHaveTextContent(
      "operator-7",
    );
  });

  it("renders the clause id for clause-scoped events", () => {
    render(
      <AuditLogTimeline
        rows={[makeRow({ clause_id: "c2" })]}
      />,
    );
    expect(screen.getByTestId("audit-timeline-clause-id")).toHaveTextContent(
      "clause: c2",
    );
  });

  it("omits the clause id line for pipeline-lifecycle events", () => {
    render(
      <AuditLogTimeline
        rows={[makeRow({ decision_type: "graph_started", clause_id: "" })]}
      />,
    );
    expect(
      screen.queryByTestId("audit-timeline-clause-id"),
    ).not.toBeInTheDocument();
  });

  it("renders the header by default; suppresses it when showHeader=false", () => {
    const { rerender } = render(
      <AuditLogTimeline rows={[makeRow()]} />,
    );
    expect(screen.getByTestId("audit-timeline-header")).toBeInTheDocument();
    rerender(<AuditLogTimeline rows={[makeRow()]} showHeader={false} />);
    expect(screen.queryByTestId("audit-timeline-header")).not.toBeInTheDocument();
  });
});
