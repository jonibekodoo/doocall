/** Server-side renderer for the structured recording guide.
 * Landing tokens, restrained visuals: no emoji noise, a few brand chips.
 * Inline markup in strings: **bold**, *italic*, `code`, [label](url). */

import type { ReactNode } from "react";

import type { GuideBlock, GuideSection } from "@/content/recording-guide.types";

// ── Inline mini-markdown ────────────────────────────────────────────────────
const INLINE =
  /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\((?:https?:\/\/)[^)]+\))/g;

function renderInline(text: string): ReactNode[] {
  return text.split(INLINE).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**"))
      return <b key={index}>{part.slice(2, -2)}</b>;
    if (part.startsWith("`") && part.endsWith("`"))
      return (
        <code
          key={index}
          className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[0.85em]"
        >
          {part.slice(1, -1)}
        </code>
      );
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2)
      return <i key={index}>{part.slice(1, -1)}</i>;
    const link = part.match(/^\[([^\]]+)\]\((https?:\/\/[^)]+)\)$/);
    if (link)
      return (
        <a
          key={index}
          href={link[2]}
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent"
        >
          {link[1]}
        </a>
      );
    return part;
  });
}

// ── Callout palette ────────────────────────────────────────────────────────
const CALLOUT: Record<string, string> = {
  note: "border-border bg-surface-2/60",
  tip: "border-accent/30 bg-accent-soft/50",
  warn: "border-warning/40 bg-warning/10",
  danger: "border-danger/40 bg-danger/5",
};

const TONE_DOT: Record<string, string> = {
  default: "bg-accent",
  samsung: "bg-[#1428A0]",
  xiaomi: "bg-[#FF6900]",
  huawei: "bg-[#CF0A2C]",
};

function Block({ block }: { block: GuideBlock }) {
  switch (block.t) {
    case "p":
      return (
        <p className="text-[15px] leading-relaxed text-fg-muted">
          {renderInline(block.text)}
        </p>
      );
    case "h3":
      return <h3 className="pt-2 text-base font-semibold">{block.text}</h3>;
    case "note":
    case "tip":
    case "warn":
    case "danger":
      return (
        <div
          className={`rounded-lg border px-4 py-3 text-sm leading-relaxed ${CALLOUT[block.t]}`}
        >
          {renderInline(block.text)}
        </div>
      );
    case "steps":
      return (
        <ol className="space-y-2">
          {block.items.map((item, index) => (
            <li key={index} className="flex gap-3 text-[15px] leading-relaxed">
              <span className="tnum mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-bold text-accent">
                {index + 1}
              </span>
              <span className="text-fg-muted">{renderInline(item)}</span>
            </li>
          ))}
        </ol>
      );
    case "list":
      return (
        <ul className="space-y-1.5 pl-1">
          {block.items.map((item, index) => (
            <li
              key={index}
              className="flex gap-2.5 text-[15px] leading-relaxed"
            >
              <span className="mt-2 size-1.5 shrink-0 rounded-full bg-accent" />
              <span className="text-fg-muted">{renderInline(item)}</span>
            </li>
          ))}
        </ul>
      );
    case "table":
      return (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-surface-2 text-left text-xs uppercase tracking-wide text-fg-muted">
              <tr>
                {block.head.map((cell, index) => (
                  <th key={index} className="px-3.5 py-2.5 font-semibold">
                    {cell}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {block.rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <td
                      key={cellIndex}
                      className="px-3.5 py-2.5 align-top leading-relaxed text-fg-muted"
                    >
                      {renderInline(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case "details":
      return (
        <details
          open={block.open}
          className="group rounded-lg border border-border bg-surface"
        >
          <summary className="cursor-pointer select-none px-4 py-3 text-sm font-semibold marker:content-none [&::-webkit-details-marker]:hidden">
            <span className="mr-2 inline-block text-fg-faint transition-transform group-open:rotate-90">
              ›
            </span>
            {block.summary}
          </summary>
          <div className="space-y-3 border-t border-border px-4 py-4">
            {block.blocks.map((child, index) => (
              <Block key={index} block={child} />
            ))}
          </div>
        </details>
      );
    case "links":
      return (
        <div className="flex flex-wrap gap-2">
          {block.items.map((item, index) => (
            <a
              key={index}
              href={item.href}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-md border border-border px-3.5 py-2 text-sm font-medium hover:border-accent hover:text-accent"
            >
              {item.label}
            </a>
          ))}
        </div>
      );
    case "video":
      return (
        <a
          href={block.href}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-3 rounded-lg border border-border bg-surface px-4 py-3 text-sm font-medium hover:border-accent"
        >
          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-accent text-accent-fg">
            ▶
          </span>
          {block.label}
        </a>
      );
  }
}

export function GuideSectionView({ section }: { section: GuideSection }) {
  return (
    <section id={section.id} className="scroll-mt-24">
      <h2 className="mb-4 flex items-center gap-2.5 text-xl font-bold sm:text-2xl">
        <span
          className={`size-2.5 rounded-full ${TONE_DOT[section.tone ?? "default"]}`}
        />
        {section.title}
      </h2>
      <div className="space-y-4">
        {section.blocks.map((block, index) => (
          <Block key={index} block={block} />
        ))}
      </div>
    </section>
  );
}
