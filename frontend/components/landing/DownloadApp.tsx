"use client";

/** Landing "download the Android app" button — shown only when an APK
 * build has been uploaded from the admin portal; always serves the
 * newest version via /api/public/app/download. */

import { Smartphone } from "lucide-react";
import { useEffect, useState } from "react";

export function DownloadApp({ label }: { label: string }) {
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/public/app/latest")
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => setVersion(body?.release?.version ?? null))
      .catch(() => setVersion(null));
  }, []);

  if (!version) return null;

  return (
    <a
      href="/api/public/app/download"
      data-testid="download-apk"
      className="inline-flex items-center gap-2 rounded-md border border-white/20 px-6 py-3 text-sm font-medium text-white/90 hover:bg-white/5"
    >
      <Smartphone className="size-4" />
      {label}
      <span className="tnum rounded-full bg-white/10 px-2 py-0.5 text-xs text-white/60">
        v{version}
      </span>
    </a>
  );
}
