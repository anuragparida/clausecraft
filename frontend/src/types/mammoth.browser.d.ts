// Type declarations for mammoth's browser bundle. The
// browser build (``mammoth/mammoth.browser``) is a UMD
// module — Vite's interop gives us either a default
// export or the namespace carrying the mammoth object.
// The official ``mammoth`` package ships its own
// ``lib/index.d.ts`` for the Node entry; the browser
// build is a separate sub-path that doesn't carry
// types. We declare it here so callers can use the
// browser bundle without ``@ts-ignore``.
//
// This file is a minimal shim — the project only uses
// ``convertToHtml`` from the mammoth API. The full type
// surface lives in ``mammoth`` (the Node entry); we
// re-declare just the browser subset.

declare module "mammoth/mammoth.browser" {
  export interface ConvertToHtmlResult {
    value: string;
    messages: ReadonlyArray<unknown>;
  }
  export interface ConvertToHtmlInput {
    arrayBuffer: ArrayBuffer;
  }
  export interface MammothBrowser {
    convertToHtml(input: ConvertToHtmlInput): Promise<ConvertToHtmlResult>;
    extractRawText(input: ConvertToHtmlInput): Promise<ConvertToHtmlResult>;
  }
  const mammoth: MammothBrowser;
  export default mammoth;
  // The UMD bundle also exposes the functions on the
  // module namespace directly; surface them so callers
  // can do either ``mammoth.convertToHtml(...)`` or
  // ``m.convertToHtml(...)``.
  export const convertToHtml: (
    input: ConvertToHtmlInput,
  ) => Promise<ConvertToHtmlResult>;
  export const extractRawText: (
    input: ConvertToHtmlInput,
  ) => Promise<ConvertToHtmlResult>;
}
