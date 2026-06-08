import { useEffect, useState } from "react";

// useHashRoute — minimal client-side URL routing for the
// Phase 3 app. Vite's dev server has no history fallback, so
// we use the URL hash (``#/path?query``) to drive navigation
// without a server-side rewrite. In production a real router
// (react-router-dom) would replace this — the spec defers
// that to Phase 5.
//
// Returned value
// --------------
// - ``path`` — the path portion (e.g. ``/contracts/abc/review``).
//   Hash routing strips the leading ``#``.
// - ``params`` — query-string parameters (parsed with
//   ``URLSearchParams``). Empty for routes that don't use them.
// - ``navigate(to)`` — replace the current hash with ``to``.
//   A path is allowed with or without a leading ``/``; we
//   always store the leading-slash form.
//
// Why hash routing here
// ---------------------
// 1. The dev server (Vite :15173) has no history fallback, so
//    a deep link to ``/contracts/.../review`` would 404 the
//    page. Hash routing keeps the page asset always at
//    ``/`` and uses the fragment for the route.
// 2. No new dep (react-router-dom is a 50KB+ install). The
//    routing surface is small (3-4 routes) and the data
//    model is captured in the URL — perfect for a hand-rolled
//    hook.

export interface HashRoute {
  /** Path portion, always starts with ``/``. ``"/"`` for the home view. */
  path: string;
  /** Query-string parameters. */
  params: URLSearchParams;
}

export interface UseHashRouteResult extends HashRoute {
  /** Navigate to a new path (preserves the existing query by default). */
  navigate: (to: string, options?: { replace?: boolean; query?: URLSearchParams }) => void;
}

function parseHash(): HashRoute {
  // Default to "/" when the hash is empty.
  const raw = window.location.hash || "#/";
  const stripped = raw.startsWith("#") ? raw.slice(1) : raw;
  // Split off any query string.
  const qIndex = stripped.indexOf("?");
  let path: string;
  let query = "";
  if (qIndex === -1) {
    path = stripped;
  } else {
    path = stripped.slice(0, qIndex);
    query = stripped.slice(qIndex + 1);
  }
  if (!path.startsWith("/")) path = "/" + path;
  if (path.length > 1 && path.endsWith("/")) {
    // Drop trailing slash for canonical form.
    path = path.slice(0, -1);
  }
  return { path, params: new URLSearchParams(query) };
}

export function useHashRoute(): UseHashRouteResult {
  const [route, setRoute] = useState<HashRoute>(() => parseHash());

  useEffect(() => {
    const handler = () => setRoute(parseHash());
    window.addEventListener("hashchange", handler);
    // Re-parse on mount in case the URL changed between
    // the initial state and the effect attaching.
    handler();
    return () => window.removeEventListener("hashchange", handler);
  }, []);

  const navigate = (
    to: string,
    options?: { replace?: boolean; query?: URLSearchParams },
  ) => {
    let next = to;
    if (!next.startsWith("/")) next = "/" + next;
    if (next.length > 1 && next.endsWith("/")) next = next.slice(0, -1);
    const queryString = options?.query?.toString() ?? "";
    const fullHash = "#" + next + (queryString ? "?" + queryString : "");
    if (options?.replace) {
      window.location.replace(fullHash);
    } else {
      window.location.hash = fullHash;
    }
  };

  return { ...route, navigate };
}

/**
 * Match a path against a pattern with ``:name`` placeholders.
 * Returns the captured params or null when the path doesn't
 * match. Pure function; the hook above is just the wiring.
 */
export function matchPath(
  pattern: string,
  path: string,
): Record<string, string> | null {
  const patternSegs = pattern.split("/").filter(Boolean);
  const pathSegs = path.split("/").filter(Boolean);
  if (patternSegs.length !== pathSegs.length) return null;
  const out: Record<string, string> = {};
  for (let i = 0; i < patternSegs.length; i++) {
    const p = patternSegs[i];
    const v = pathSegs[i];
    if (p.startsWith(":")) {
      out[p.slice(1)] = decodeURIComponent(v);
    } else if (p !== v) {
      return null;
    }
  }
  return out;
}
