import { PhoneCall } from "lucide-react";

export function AuthCard({
  title,
  children,
  footer,
}: {
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div className="grid min-h-screen place-items-center bg-bg p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2">
          <span className="grid size-9 place-items-center rounded-md bg-accent text-accent-fg">
            <PhoneCall className="size-4" />
          </span>
          <span className="font-[family-name:var(--font-display)] text-xl font-semibold">
            dooCall
          </span>
        </div>
        <div className="rounded-lg border border-border bg-surface p-6 shadow-md">
          <h1 className="mb-4 text-lg font-semibold">{title}</h1>
          {children}
        </div>
        {footer && (
          <div className="mt-4 text-center text-sm text-fg-muted">{footer}</div>
        )}
      </div>
    </div>
  );
}

export function Field({
  label,
  ...props
}: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="mb-3 block">
      <span className="mb-1 block text-xs font-medium text-fg-muted">
        {label}
      </span>
      <input
        {...props}
        className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm placeholder:text-fg-faint focus:border-accent"
      />
    </label>
  );
}

export function SubmitButton({
  children,
  loading,
}: {
  children: React.ReactNode;
  loading?: boolean;
}) {
  return (
    <button
      type="submit"
      disabled={loading}
      className="mt-1 w-full rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-accent-fg hover:opacity-90 disabled:opacity-50"
    >
      {loading ? "…" : children}
    </button>
  );
}
