"use client";

/** Landing "Integrations" strip: the built-in connectors + the admin-managed
 * CRM catalog (same tiles the cabinet shows), fetched from the public API. */

import { useEffect, useState } from "react";

interface Tile {
  id: number;
  name: string;
  site_url: string;
  logo_url: string | null;
}

const SPECIAL = [
  {
    key: "bitrix24",
    href: "/docs/bitrix24",
    logo: (
      <span className="text-lg font-extrabold" style={{ color: "#0BA7EF" }}>
        Bitrix<span className="text-[#005893]">24</span>
      </span>
    ),
  },
  {
    key: "amocrm",
    href: "/docs/amocrm",
    logo: (
      <span className="text-lg font-bold italic" style={{ color: "#339DC7" }}>
        amoCRM.
      </span>
    ),
  },
  {
    key: "odoo",
    href: "/docs/api",
    logo: (
      <span className="text-lg font-extrabold" style={{ color: "#714B67" }}>
        odoo
      </span>
    ),
  },
] as const;

export function IntegrationsSection({
  strings,
}: {
  strings: { title: string; text: string };
}) {
  const [entries, setEntries] = useState<Tile[]>([]);
  useEffect(() => {
    fetch("/api/public/crm-catalog")
      .then((response) => response.json())
      .then((body) => setEntries(body.entries ?? []))
      .catch(() => {});
  }, []);

  return (
    <section id="integrations" className="mx-auto max-w-6xl px-6 py-20">
      <h2 className="text-center font-[family-name:var(--font-display)] text-3xl font-bold">
        {strings.title}
      </h2>
      <p className="mx-auto mt-2 max-w-xl text-center text-sm text-fg-muted">
        {strings.text}
      </p>
      <div className="mt-8 flex flex-wrap justify-center gap-3">
        {SPECIAL.map((tile) => (
          <a
            key={tile.key}
            href={tile.href}
            className="grid h-20 w-44 place-items-center rounded-lg border border-border bg-white transition hover:-translate-y-0.5 hover:shadow-md dark:bg-surface-2"
          >
            {tile.logo}
          </a>
        ))}
        {entries.map((entry) => (
          <a
            key={entry.id}
            href={entry.site_url}
            target="_blank"
            rel="noreferrer noopener"
            className="grid h-20 w-44 place-items-center rounded-lg border border-border bg-white p-2 transition hover:-translate-y-0.5 hover:shadow-md dark:bg-surface-2"
          >
            {entry.logo_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={entry.logo_url}
                alt={entry.name}
                className="max-h-14 max-w-full object-contain"
              />
            ) : (
              <span className="text-center text-sm font-semibold text-fg-muted">
                {entry.name}
              </span>
            )}
          </a>
        ))}
      </div>
    </section>
  );
}
