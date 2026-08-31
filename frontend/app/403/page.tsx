import Link from "next/link";

export default function ForbiddenPage() {
  return (
    <div className="grid min-h-screen place-items-center bg-bg p-4">
      <div
        data-testid="forbidden"
        className="max-w-sm rounded-lg border border-border bg-surface p-8 text-center shadow-md"
      >
        <p className="font-[family-name:var(--font-display)] text-5xl font-bold text-danger">
          403
        </p>
        <p className="mt-3 text-sm text-fg-muted">
          У вас нет доступа к этому разделу.
        </p>
        <Link
          href="/login"
          className="mt-5 inline-block rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-fg"
        >
          Войти
        </Link>
      </div>
    </div>
  );
}
