import { describe, it, expect } from "vitest";
import { matchPath } from "@/lib/router";

// matchPath — pure-function pattern matcher. The router
// surface is small; covering the branches here keeps the
// App.tsx routing code honest.

describe("matchPath", () => {
  it("matches exact paths with no params", () => {
    expect(matchPath("/triage", "/triage")).toEqual({});
  });

  it("captures :name placeholders", () => {
    expect(matchPath("/contracts/:id/review", "/contracts/abc/review")).toEqual({
      id: "abc",
    });
  });

  it("URL-decodes the captured value", () => {
    expect(
      matchPath("/contracts/:id/review", "/contracts/abc%20123/review"),
    ).toEqual({ id: "abc 123" });
  });

  it("returns null when the segment count differs", () => {
    expect(matchPath("/triage", "/triage/extra")).toBeNull();
  });

  it("returns null when a literal segment doesn't match", () => {
    expect(matchPath("/contracts/:id/review", "/contracts/abc/audit")).toBeNull();
  });

  it("returns null when the path is empty", () => {
    expect(matchPath("/triage", "/")).toBeNull();
  });
});
