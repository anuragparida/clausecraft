import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

  it("renders the spec-287 tracked-changes disclaimer (safety net, mandatory in UI)", async () => {
    globalThis.fetch = vi.fn(async () => makeDocxResponse()) as typeof fetch;
    render(
      withQueryClient(
        <RedlineOutputPage
          contractId="demo-001"
          onBackToHome={() => {}}
        />,
      ),
    );
    // The disclaimer element MUST be in the DOM (spec line 287).
    // The exact wording matches the spec's intent: the
    // browser preview cannot show tracked changes; the user
    // has to open the .docx to see them.
    const disclaimer = await screen.findByTestId(
      "redline-tracked-changes-disclaimer",
    );
    expect(disclaimer).toBeInTheDocument();
    expect(disclaimer).toHaveTextContent(/Tracked changes don['’]t appear/i);
    expect(disclaimer).toHaveTextContent(/Download the .docx/);
  });

  it("renders both Download .docx and Download .md buttons", async () => {
    globalThis.fetch = vi.fn(async () => makeDocxResponse()) as typeof fetch;
    render(
      withQueryClient(
        <RedlineOutputPage
          contractId="demo-001"
          onBackToHome={() => {}}
        />,
      ),
    );
    // Wait for the auto-download to finish: the button
    // label flips from "Downloading…" back to "Download .docx"
    // once the .docx blob is in cache and the page
    // has rendered the preview-card with both buttons.
    await waitFor(() => {
      expect(
        screen.getByTestId("redline-download-button"),
      ).toHaveTextContent("Download .docx");
    });
    expect(
      screen.getByTestId("redline-download-md-button"),
    ).toHaveTextContent("Download .md");
  });

  it("Download .md button calls /redline.md endpoint", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response("---\n# redline diff\n+ new text\n", {
        status: 200,
        headers: { "content-type": "text/markdown; charset=utf-8" },
      }),
    ) as typeof fetch;
    const user = userEvent.setup();
    render(
      withQueryClient(
        <RedlineOutputPage
          contractId="demo-001"
          onBackToHome={() => {}}
        />,
      ),
    );
    await waitFor(() => {
      expect(
        screen.getByTestId("redline-download-md-button"),
      ).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("redline-download-md-button"));
    await waitFor(() => {
      const mdCalls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls
        .filter((c) => String(c[0]).includes("/redline.md"));
      expect(mdCalls.length).toBeGreaterThan(0);
    });
  });
});
