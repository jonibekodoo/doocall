"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "@/lib/api/client";
import { AuthProvider } from "@/lib/auth";
import { ToastProvider, useToastStore } from "@/components/ui/Toast";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: (failureCount, error) => {
              // Never retry auth/paywall failures; twice for the rest.
              if (
                error instanceof ApiError &&
                [401, 402, 403].includes(error.status)
              )
                return false;
              return failureCount < 2;
            },
            staleTime: 15_000,
          },
          mutations: {
            onError: (error) => {
              useToastStore.getState().push({
                kind: "error",
                text: error instanceof Error ? error.message : "Error",
              });
            },
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ToastProvider>{children}</ToastProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
