"use client";

/** Map pin for a call row: on click fetches the call detail (latitude /
 * longitude / address) and opens a modal with an OpenStreetMap embed plus a
 * Google Maps link. Rendered only for rows that report `has_location`. */

import { ExternalLink, MapPin, X } from "lucide-react";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { fetchCallDetail } from "@/lib/api/endpoints";

type Loc = { lat: number; lng: number; address: string };

export function CallMapButton({ callId }: { callId: number }) {
  const t = useTranslations("callMap");
  const [loc, setLoc] = useState<Loc | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    if (loc) {
      setOpen(true);
      return;
    }
    setLoading(true);
    try {
      const detail = await fetchCallDetail(callId);
      const { latitude, longitude, address } = detail.call;
      if (latitude != null && longitude != null) {
        setLoc({ lat: latitude, lng: longitude, address });
        setOpen(true);
      }
    } finally {
      setLoading(false);
    }
  };

  const d = 0.005; // ~500 m box around the pin
  const embed = loc
    ? `https://www.openstreetmap.org/export/embed.html?bbox=${loc.lng - d},${loc.lat - d},${loc.lng + d},${loc.lat + d}&layer=mapnik&marker=${loc.lat},${loc.lng}`
    : "";
  const gmaps = loc ? `https://www.google.com/maps?q=${loc.lat},${loc.lng}` : "";

  return (
    <>
      <button
        type="button"
        data-testid="row-map"
        onClick={load}
        disabled={loading}
        aria-label="map"
        title={t("title")}
        className="grid size-7 shrink-0 place-items-center rounded-full bg-accent-soft text-accent hover:bg-accent hover:text-accent-fg disabled:animate-pulse"
      >
        <MapPin className="size-3.5" />
      </button>

      {open && loc && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4"
          role="dialog"
          onClick={() => setOpen(false)}
        >
          <div
            className="w-full max-w-2xl overflow-hidden rounded-xl border border-border bg-surface shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 border-b border-border px-4 py-3">
              <MapPin className="size-4 text-accent" />
              <h2 className="text-sm font-semibold">{t("title")}</h2>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="close"
                className="ml-auto rounded-md p-1 text-fg-muted hover:bg-surface-2 hover:text-fg"
              >
                <X className="size-4" />
              </button>
            </div>
            <iframe
              title="map"
              src={embed}
              className="h-80 w-full border-0"
              loading="lazy"
            />
            <div className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
              <div className="min-w-0 flex-1">
                {loc.address && <p className="truncate text-fg">{loc.address}</p>}
                <p className="tnum text-xs text-fg-faint">
                  {loc.lat.toFixed(6)}, {loc.lng.toFixed(6)}
                </p>
              </div>
              <a
                href={gmaps}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-accent-fg hover:opacity-90"
              >
                <ExternalLink className="size-3.5" />
                {t("open")}
              </a>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
