"use client";

/** Persistent banner while a superadmin is impersonating a company (A.3). */

import { Eye, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { impersonateStop } from "@/lib/api/admin";
import { setAccessToken, tryRefresh } from "@/lib/api/client";

export function ImpersonationBanner() {
  const router = useRouter();
  const [info, setInfo] = useState<{ company: string; user: string } | null>(
    null,
  );

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem("doocall_impersonation");
      if (raw) {
        const parsed = JSON.parse(raw);
        setAccessToken(parsed.token); // impersonation token wins in this tab
        setInfo({ company: parsed.company, user: parsed.user });
      }
    } catch {
      /* corrupted flag → ignore */
    }
  }, []);

  if (!info) return null;

  const exit = async () => {
    sessionStorage.removeItem("doocall_impersonation");
    setAccessToken(null);
    await tryRefresh(); // admin's own refresh cookie restores their session
    try {
      await impersonateStop(info.company);
    } catch {
      /* audit best-effort */
    }
    router.push("/admin");
  };

  return (
    <div
      data-testid="impersonation-banner"
      className="sticky top-0 z-50 flex items-center justify-center gap-3 bg-warning px-4 py-2 text-sm font-semibold text-[#3d2e00]"
    >
      <Eye className="size-4" />
      Режим просмотра: {info.user} ({info.company})
      <button
        type="button"
        data-testid="impersonation-exit"
        onClick={exit}
        className="flex items-center gap-1 rounded-md bg-black/10 px-2.5 py-1 text-xs font-bold hover:bg-black/20"
      >
        <X className="size-3.5" /> Выйти в админку
      </button>
    </div>
  );
}
