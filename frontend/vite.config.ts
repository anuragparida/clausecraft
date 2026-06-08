/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Vite + Vitest config for clausecraft frontend.
// Port matches docker-compose `FRONTEND_PORT` (15173 by default).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: Number(process.env.VITE_PORT) || 15173,
    strictPort: true,
    // Proxy /api/* to the FastAPI backend. Inside the docker-compose
    // network the backend is reachable as ``http://backend:8000``.
    // From a local dev (no docker) the override is
    // ``VITE_API_TARGET=http://localhost:18000``. Phase 1 calls
    // POST /api/contracts/ingest from the Triage page. The proxy is
    // dev-server only; the production build would put a reverse proxy
    // in front of both services.
    //
    // Phase 3 routing:
    // - Most Phase 3 endpoints (Build 3's resume, Build 2/3's
    //   ``.docx`` download, the spot/ingest endpoints) live at
    //   ``/contracts/...`` on FastAPI. The Vite proxy strips the
    //   ``/api`` prefix so the frontend can call them as
    //   ``/api/contracts/...`` and the proxy turns it into
    //   ``/contracts/...`` on the backend.
    // - Build 4's audit-log export endpoints are registered on
    //   FastAPI as ``/api/contracts/{id}/audit-log.{json,pdf}``
    //   (the e2e test exercises the literal path). The proxy
    //   passes those paths through unchanged.
    //
    // Concretely: the rewrite keeps the existing Triage flow
    // (``/api/contracts/ingest`` → ``/contracts/ingest``) working,
    // and a route-passthrough for the Build 4 audit-log paths.
    // In production we'd put a single reverse proxy (nginx / Caddy
    // / FastAPI middleware) in front and skip the rewrite entirely.
    proxy: {
      "/api/contracts/.*/audit-log\\.(json|pdf)": {
        target:
          process.env.VITE_API_TARGET || "http://backend:8000",
        changeOrigin: true,
      },
      "/api": {
        target:
          process.env.VITE_API_TARGET || "http://backend:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  preview: {
    host: "0.0.0.0",
    port: Number(process.env.VITE_PORT) || 15173,
    strictPort: true,
  },
  // Vitest config. Phase 2 adds a UI test suite (SeverityBadge,
  // CitationPopover, DeviationReview). The tests run in jsdom —
  // @testing-library/react is the renderer. `globals: true` so
  // individual tests can use `describe/it/expect` without imports.
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
