"use client";

/** Credential reveal-once dialog (operator mobile credentials). */

import { Copy } from "lucide-react";

import type { NewOperatorResponse } from "@/lib/api/endpoints";

export function CredentialsDialog({
  credentials,
  note,
  onClose,
}: {
  credentials: NewOperatorResponse["credentials"];
  note: string;
  onClose: () => void;
}) {
  const copy = (value: string) => navigator.clipboard?.writeText(value);
  return (
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-4"
      role="dialog"
    >
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-5 shadow-lg">
        <p className="mb-3 rounded-md bg-warning/10 px-3 py-2 text-xs font-medium text-warning">
          {note}
        </p>
        <dl className="space-y-2 text-sm" data-testid="credentials">
          {(
            [
              ["login", credentials.user_name],
              ["password", credentials.password],
              ["api_key", credentials.api_key],
            ] as const
          ).map(([label, value]) => (
            <div
              key={label}
              className="flex items-center justify-between gap-2"
            >
              <dt className="text-xs uppercase text-fg-faint">{label}</dt>
              <dd className="tnum flex items-center gap-1.5 font-mono text-xs">
                {value}
                <button
                  type="button"
                  aria-label={`copy ${label}`}
                  onClick={() => copy(value)}
                  className="text-fg-faint hover:text-accent"
                >
                  <Copy className="size-3.5" />
                </button>
              </dd>
            </div>
          ))}
        </dl>
        <button
          type="button"
          data-testid="credentials-close"
          onClick={onClose}
          className="mt-4 w-full rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-fg"
        >
          OK
        </button>
      </div>
    </div>
  );
}
