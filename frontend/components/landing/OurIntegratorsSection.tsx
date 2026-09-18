"use client";

/** "Our integrators" — public strip of published integrators (logo + name).
 * Fetches /api/public/integrators; the whole section hides when empty so the
 * landing never shows a blank block. */

import { useEffect, useState } from "react";

interface PublicIntegrator {
  name: string;
  logo_url: string | null;
}

export function OurIntegratorsSection({
  strings,
}: {
  strings: { title: string; text: string };
}) {
  const [items, setItems] = useState<PublicIntegrator[] | null>(null);

  useEffect(() => {
    fetch("/api/public/integrators")
      .then((r) => r.json())
      .then((body) => setItems(body.integrators ?? []))
      .catch(() => setItems([]));
  }, []);

  // Nothing published yet → render nothing (no empty section).
  if (!items || items.length === 0) return null;

  return (
    <section className="mx-auto max-w-6xl px-6 py-20">
      <h2 className="text-center font-[family-name:var(--font-display)] text-3xl font-bold sm:text-4xl">
        {strings.title}
      </h2>
      <p className="mx-auto mt-3 max-w-xl text-center text-fg-muted">
        {strings.text}
      </p>
      <div className="mt-12 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {items.map((it, i) => (
          <div
            key={`${it.name}-${i}`}
            className="flex flex-col items-center gap-3 rounded-xl border border-border bg-surface p-6 text-center transition-shadow hover:shadow-md"
          >
            <span className="grid size-16 place-items-center overflow-hidden rounded-xl border border-border bg-surface-2 text-2xl font-bold text-fg-muted">
              {it.logo_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={it.logo_url}
                  alt={it.name}
                  className="size-full object-contain"
                />
              ) : (
                it.name.slice(0, 1).toUpperCase()
              )}
            </span>
            <span className="text-sm font-semibold">{it.name}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
