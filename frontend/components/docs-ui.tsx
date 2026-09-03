/** Shared building blocks for the public /docs pages (trilingual guides). */

import Link from "next/link";

import { PortalLocaleSwitcher } from "@/components/PortalLocaleSwitcher";

export function DocsShell({
  title,
  intro,
  apiDocsLabel,
  footer,
  children,
}: {
  title: string;
  intro: string;
  apiDocsLabel: string;
  footer: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-bg text-fg">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-3 px-4 py-4">
          <p className="font-[family-name:var(--font-display)] text-xl font-semibold">
            dooCall <span className="text-fg-muted">· Docs</span>
          </p>
          <div className="flex items-center gap-4">
            <PortalLocaleSwitcher />
            <Link
              href="/docs/api"
              className="text-sm text-accent hover:underline"
            >
              {apiDocsLabel}
            </Link>
            <Link href="/" className="text-sm text-accent hover:underline">
              doocall.uz
            </Link>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-4xl space-y-8 px-4 py-8">
        <div>
          <h1 className="text-2xl font-bold">{title}</h1>
          <p className="mt-2 text-sm leading-relaxed text-fg-muted">{intro}</p>
        </div>
        {children}
        <footer className="border-t border-border pt-6 text-xs text-fg-faint">
          {footer}
        </footer>
      </main>
    </div>
  );
}

export function DocsSection({
  step,
  title,
  children,
}: {
  step?: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-t border-border pt-6">
      <h2 className="mb-3 flex items-center gap-2.5 text-lg font-semibold">
        {step != null && (
          <span className="grid size-7 shrink-0 place-items-center rounded-full bg-accent text-sm font-bold text-accent-fg">
            {step}
          </span>
        )}
        {title}
      </h2>
      <div className="space-y-2 text-sm leading-relaxed">{children}</div>
    </section>
  );
}

export function DocsNote({
  kind = "info",
  children,
}: {
  kind?: "info" | "warning";
  children: React.ReactNode;
}) {
  return (
    <div
      className={
        kind === "warning"
          ? "rounded-md border-l-4 border-danger bg-danger/5 p-3 text-sm leading-relaxed"
          : "rounded-md border-l-4 border-accent bg-accent-soft/40 p-3 text-sm leading-relaxed"
      }
    >
      {children}
    </div>
  );
}

export function DocsCode({ children }: { children: string }) {
  return (
    <pre className="my-2 overflow-x-auto rounded-lg bg-[#14181a] p-3 text-xs leading-relaxed text-[#d7e0e4]">
      <code>{children}</code>
    </pre>
  );
}

export function DocsList({ items }: { items: React.ReactNode[] }) {
  return (
    <ul className="list-disc space-y-1 pl-5">
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  );
}
