import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  CounterpartyPicker,
  counterpartyTypeLabel,
  type CounterpartyType,
} from "@/components/CounterpartyPicker";

// CounterpartyPicker — minimal scope per the card body:
//   - 4 spec axes (enterprise / smb / public_sector /
//     healthcare) plus a legacy "any" sentinel.
//   - Renders a 4-radio group above the upload.
//   - onChange is called with the picked value.
//   - The 5 options are all present, the picked one is
//     marked as data-checked=true, the rest false.

describe("CounterpartyPicker", () => {
  it("renders all 5 options with enterprise pre-selected", () => {
    render(<CounterpartyPicker value="enterprise" onChange={() => {}} />);
    expect(screen.getByTestId("counterparty-picker")).toBeInTheDocument();
    expect(
      screen.getByTestId("counterparty-picker-option-enterprise"),
    ).toHaveAttribute("data-checked", "true");
    for (const v of ["smb", "public_sector", "healthcare", "any"] as const) {
      expect(
        screen.getByTestId(`counterparty-picker-option-${v}`),
      ).toHaveAttribute("data-checked", "false");
    }
  });

  it("marks the picked option as checked regardless of value", () => {
    const { rerender } = render(
      <CounterpartyPicker value="public_sector" onChange={() => {}} />,
    );
    expect(
      screen.getByTestId("counterparty-picker-option-public_sector"),
    ).toHaveAttribute("data-checked", "true");
    rerender(<CounterpartyPicker value="healthcare" onChange={() => {}} />);
    expect(
      screen.getByTestId("counterparty-picker-option-healthcare"),
    ).toHaveAttribute("data-checked", "true");
    rerender(<CounterpartyPicker value="any" onChange={() => {}} />);
    expect(
      screen.getByTestId("counterparty-picker-option-any"),
    ).toHaveAttribute("data-checked", "true");
  });

  it("calls onChange with the picked value when a radio is clicked", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<CounterpartyPicker value="enterprise" onChange={onChange} />);
    await user.click(screen.getByTestId("counterparty-picker-input-smb"));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith("smb");
    await user.click(
      screen.getByTestId("counterparty-picker-input-public_sector"),
    );
    expect(onChange).toHaveBeenCalledTimes(2);
    expect(onChange).toHaveBeenLastCalledWith("public_sector");
  });

  it("disables all radios when disabled=true", () => {
    render(
      <CounterpartyPicker
        value="enterprise"
        onChange={() => {}}
        disabled
      />,
    );
    for (const v of [
      "enterprise",
      "smb",
      "public_sector",
      "healthcare",
      "any",
    ] as const) {
      expect(
        screen.getByTestId(`counterparty-picker-input-${v}`),
      ).toBeDisabled();
    }
  });

  it("exposes the data-value attribute on the wrapper (test hook)", () => {
    const { rerender } = render(
      <CounterpartyPicker value="smb" onChange={() => {}} />,
    );
    expect(screen.getByTestId("counterparty-picker")).toHaveAttribute(
      "data-value",
      "smb",
    );
    rerender(<CounterpartyPicker value="healthcare" onChange={() => {}} />);
    expect(screen.getByTestId("counterparty-picker")).toHaveAttribute(
      "data-value",
      "healthcare",
    );
  });

  it("renders the help copy", () => {
    render(<CounterpartyPicker value="enterprise" onChange={() => {}} />);
    expect(
      screen.getByTestId("counterparty-picker-help"),
    ).toHaveTextContent(/matrix/i);
  });
});

describe("counterpartyTypeLabel", () => {
  it("returns a non-empty human label for every CounterpartyType", () => {
    const all: CounterpartyType[] = [
      "enterprise",
      "smb",
      "public_sector",
      "healthcare",
      "any",
    ];
    for (const v of all) {
      const label = counterpartyTypeLabel(v);
      expect(label).toBeTruthy();
      expect(typeof label).toBe("string");
    }
  });

  it("uses distinct labels per axis (no two values collapse)", () => {
    const all: CounterpartyType[] = [
      "enterprise",
      "smb",
      "public_sector",
      "healthcare",
      "any",
    ];
    const labels = all.map(counterpartyTypeLabel);
    expect(new Set(labels).size).toBe(all.length);
  });
});
