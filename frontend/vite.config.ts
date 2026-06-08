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
    proxy: {
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
