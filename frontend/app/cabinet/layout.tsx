"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { ImpersonationBanner } from "@/components/ImpersonationBanner";
import { PaywallScreen } from "@/components/PaywallScreen";
import { MobileNav, Sidebar } from "@/components/shell/Sidebar";
import { Topbar } from "@/components/shell/Topbar";
import { ApiError, get } from "@/lib/api/client";
import type { BillingStatusResponse, PaywallPayload } from "@/lib/api/types";
import { RequireAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

function useBillingGate(): { paywall: PaywallPayload | null; ready: boolean } {
  const { data, error, isPending } = useQuery({
    queryKey: ["billing-status"],
    queryFn: () => get<BillingStatusResponse>("/billing/status"),
    staleTime: 60_000,
  });
  if (error instanceof ApiError && error.status === 402) {
    const body = error.body as BillingStatusResponse;
    return { paywall: body?.paywall ?? null, ready: true };
  }
  return { paywall: null, ready: !isPending || Boolean(data) };
}

function CabinetShell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const { paywall, ready } = useBillingGate();

  useEffect(() => {
    setCollapsed(localStorage.getItem("doocall_sidebar") === "collapsed");
  }, []);
  const toggle = () => {
    setCollapsed((value) => {
      localStorage.setItem("doocall_sidebar", value ? "open" : "collapsed");
      return !value;
    });
  };

  if (paywall) return <PaywallScreen paywall={paywall} />;

  return (
    <div className="min-h-screen bg-bg" data-testid="cabinet-shell">
      <ImpersonationBanner />
      <Sidebar collapsed={collapsed} onToggle={toggle} />
      <div
        className={cn(
          "transition-[margin] duration-200",
          collapsed
            ? "sm:ml-[var(--sidebar-w-collapsed)]"
            : "sm:ml-[var(--sidebar-w)]",
        )}
      >
        <Topbar />
        <MobileNav />
        <main className="mx-auto min-w-[340px] max-w-[1400px] p-4 md:p-6">
          {ready ? (
            children
          ) : (
            <div className="animate-pulse text-fg-faint">…</div>
          )}
        </main>
      </div>
    </div>
  );
}

export default function CabinetLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <RequireAuth>
      <CabinetShell>{children}</CabinetShell>
    </RequireAuth>
  );
}
