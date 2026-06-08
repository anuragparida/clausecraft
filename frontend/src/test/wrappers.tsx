import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

// makeQueryClient — fresh QueryClient per test. Sharing a
// QueryClient between tests causes cross-test cache pollution
// (a successful query in test A is still cached in test B).
//
// The default config disables retries and the deduping
// interval so test failures are deterministic — a flaky
// network call never gets a second chance.

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

export function withQueryClient(children: ReactNode) {
  const qc = makeQueryClient();
  return (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}
