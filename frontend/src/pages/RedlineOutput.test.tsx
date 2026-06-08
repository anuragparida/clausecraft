import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { withQueryClient } from "@/test/wrappers";
import { RedlineOutputPage } from "@/pages/RedlineOutput";

// RedlineOutput: download the .docx on mount, render the
// mammoth preview. We mock fetch to return a fake
// ``application/vnd.openxmlformats-officedocument...``
// response and stub the mammoth module so the preview
// renders without pulling in the real library.

const originalFetch = globalThis.fetch;
const originalCreateObjectURL = URL.createObjectURL;
const originalRevokeObjectURL = URL.revokeObjectURL;

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:mock") as typeof URL.createObjectURL;
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  URL.createObjectURL = originalCreateObjectURL;
  URL.revokeObjectURL = originalRevokeObjectURL;
  vi.restoreAllMocks();
  vi.unmock("mammoth/mammoth.browser");
});

function makeDocxResponse() {
  // We don't need a real .docx; the RedlineOutput page
  // just hands the bytes to mammoth and renders the
  // resulting HTML. Mammoth is mocked below.
  return new Response(new Uint8Array([0x50, 0x4b, 0x03, 0x04]), {
    status: 200,
    headers: {
      "content-type":
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
  });
}

describe("RedlineOutputPage", () => {
  it("renders the loading state on first mount", () => {
    globalThis.fetch = vi.fn(
      () =>
        new Promise<Response>(() => {
          /* never resolves */
        }),
    ) as typeof fetch;
    render(
      withQueryClient(
        <RedlineOutputPage
          contractId="demo-001"
          onBackToHome={() => {}}
        />,
      ),
    );
    expect(screen.getByTestId("redline-loading")).toBeInTheDocument();
  });

  it("renders the error state on a failed fetch", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response("server boom", { status: 500 }),
    ) as typeof fetch;
    render(
      withQueryClient(
        <RedlineOutputPage
          contractId="demo-001"
          onBackToHome={() => {}}
        />,
      ),
    );
    await waitFor(() => {
      expect(screen.getByTestId("redline-error")).toBeInTheDocument();
    });
  });

  it("fetches the .docx from the right endpoint on mount", async () => {
    globalThis.fetch = vi.fn(async () => makeDocxResponse()) as typeof fetch;
    render(
      withQueryClient(
        <RedlineOutputPage
          contractId="demo-001"
          onBackToHome={() => {}}
        />,
      ),
    );
    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/contracts/demo-001/redline.docx"),
      );
    });
  });
});
