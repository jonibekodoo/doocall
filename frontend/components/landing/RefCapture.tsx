"use client";

/** Captures ?ref=CODE from the landing URL into a 30-day cookie (A.4).
 * Registration reads it and binds the company to the integrator. */

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";

export const REF_COOKIE = "doocall_ref";

export function readRefCookie(): string | null {
  const match = document.cookie.match(/doocall_ref=([A-Za-z0-9]+)/);
  return match ? match[1] : null;
}

function Inner() {
  const params = useSearchParams();
  useEffect(() => {
    const ref = params.get("ref");
    if (ref && /^[A-Za-z0-9]{4,12}$/.test(ref)) {
      document.cookie = `${REF_COOKIE}=${ref.toUpperCase()};path=/;max-age=${30 * 86400};samesite=lax`;
    }
  }, [params]);
  return null;
}

export function RefCapture() {
  return (
    <Suspense>
      <Inner />
    </Suspense>
  );
}
