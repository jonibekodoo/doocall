"use client";

/** Temp-password reveal-once panel (A.4 manual registration). */

import { Check, Copy } from "lucide-react";
import { useState } from "react";

export function generateTempPassword(length = 12): string {
  const alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789";
  const bytes = new Uint32Array(length);
  crypto.getRandomValues(bytes);
  return [...bytes].map((b) => alphabet[b % alphabet.length]).join("");
}

export function TempPasswordReveal({
  password,
  email,
  note,
  onDone,
}: {
  password: string;
  email: string;
  note: string;
  onDone: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(password);
    setCopied(true);
  };
  return (
    <div
      data-testid="temp-password"
      className="rounded-lg border border-warning/50 bg-warning/10 p-4"
    >
      <p className="text-xs font-semibold text-warning">{note}</p>
      <div className="mt-2 flex items-center gap-2">
        <code className="tnum flex-1 rounded bg-surface px-3 py-2 font-mono text-sm">
          {password}
        </code>
        <button
          type="button"
          data-testid="temp-password-copy"
          onClick={copy}
          aria-label="copy"
          className="grid size-9 place-items-center rounded-md border border-border bg-surface hover:bg-surface-2"
        >
          {copied ? (
            <Check className="size-4 text-accent" />
          ) : (
            <Copy className="size-4" />
          )}
        </button>
      </div>
      <div className="mt-3 flex gap-2">
        <a
          href={`mailto:${email}?subject=dooCall&body=Login: ${email}%0APassword: ${password}`}
          className="rounded-md border border-border bg-surface px-3 py-1.5 text-xs font-medium hover:bg-surface-2"
        >
          ✉ {email}
        </a>
        <button
          type="button"
          data-testid="temp-password-done"
          onClick={onDone}
          className="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-accent-fg"
        >
          OK
        </button>
      </div>
    </div>
  );
}
