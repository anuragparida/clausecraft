import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SeverityBadge } from "@/components/SeverityBadge";

// SeverityBadge maps 0..3 to the right colour-coded variant.
//
// What we test:
//   1. Each score renders with the right `data-severity` attr
//      and an "S{n}" label so visual mapping is test-stable.
//   2. The badge always has a non-empty label and is reachable
//      by data-testid.
//   3. Out-of-range scores clamp to 0 (defensive default).

describe("SeverityBadge", () => {
  it("renders score 0 as S0 with the sev-0 colour variant", () => {
    render(<SeverityBadge score={0} />);
    const badge = screen.getByTestId("severity-badge");
    expect(badge).toHaveTextContent("S0");
    expect(badge).toHaveAttribute("data-severity", "0");
    expect(badge.className).toMatch(/emerald/);
  });

  it("renders score 1 as S1 with the sev-1 colour variant (yellow)", () => {
    render(<SeverityBadge score={1} />);
    const badge = screen.getByTestId("severity-badge");
    expect(badge).toHaveTextContent("S1");
    expect(badge).toHaveAttribute("data-severity", "1");
    expect(badge.className).toMatch(/amber/);
  });

  it("renders score 2 as S2 with the sev-2 colour variant (orange)", () => {
    render(<SeverityBadge score={2} />);
    const badge = screen.getByTestId("severity-badge");
    expect(badge).toHaveTextContent("S2");
    expect(badge).toHaveAttribute("data-severity", "2");
    expect(badge.className).toMatch(/orange/);
  });

  it("renders score 3 as S3 with the sev-3 colour variant (red)", () => {
    render(<SeverityBadge score={3} />);
    const badge = screen.getByTestId("severity-badge");
    expect(badge).toHaveTextContent("S3");
    expect(badge).toHaveAttribute("data-severity", "3");
    expect(badge.className).toMatch(/red/);
  });

  it("clamps out-of-range scores to 0 (defensive default)", () => {
    const { rerender } = render(<SeverityBadge score={-1} />);
    expect(screen.getByTestId("severity-badge")).toHaveAttribute(
      "data-severity",
      "0"
    );

    // Re-render with a different value to confirm the clamp is
    // per-render, not a module-level cache.
    rerender(<SeverityBadge score={42} />);
    expect(screen.getByTestId("severity-badge")).toHaveAttribute(
      "data-severity",
      "0"
    );
  });

  it("honours a custom label override", () => {
    render(<SeverityBadge score={2} label="Material" />);
    expect(screen.getByTestId("severity-badge")).toHaveTextContent(
      "Material"
    );
  });
});
