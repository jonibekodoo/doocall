"use client";

/** In-app replacement for window.confirm / window.prompt: a promise-based
 * store + one modal host (same pattern as the toast system, no deps). */

import { useTranslations } from "next-intl";
import { useState, useSyncExternalStore } from "react";

interface DialogState {
  message: string;
  danger?: boolean;
  confirmLabel?: string;
  input?: boolean;
  defaultValue?: string;
  resolve: (result: string | boolean | null) => void;
}

let current: DialogState | null = null;
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Styled in-app confirm. Resolves true only on the confirm button. */
export function confirmDialog(
  message: string,
  opts: { danger?: boolean; confirmLabel?: string } = {},
): Promise<boolean> {
  return new Promise((resolve) => {
    current = { message, ...opts, resolve: (r) => resolve(r === true) };
    emit();
  });
}

/** Styled in-app prompt. Resolves the string, or null when cancelled. */
export function promptDialog(
  message: string,
  defaultValue = "",
): Promise<string | null> {
  return new Promise((resolve) => {
    current = {
      message,
      input: true,
      defaultValue,
      resolve: (r) => resolve(typeof r === "string" ? r : null),
    };
    emit();
  });
}

function DialogBody({ state }: { state: DialogState }) {
  const t = useTranslations("common");
  const [value, setValue] = useState(state.defaultValue ?? "");

  const close = (result: string | boolean | null) => {
    const active = current;
    current = null;
    emit();
    active?.resolve(result);
  };

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      data-testid="app-confirm"
    >
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-5 shadow-lg">
        <p className="text-sm leading-relaxed">{state.message}</p>
        {state.input && (
          <input
            autoFocus
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") close(value);
              if (event.key === "Escape") close(null);
            }}
            data-testid="app-prompt-input"
            className="tnum mt-3 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
          />
        )}
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            data-testid="app-confirm-cancel"
            onClick={() => close(state.input ? null : false)}
            className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-surface-2"
          >
            {t("cancel")}
          </button>
          <button
            type="button"
            data-testid="app-confirm-ok"
            onClick={() => close(state.input ? value : true)}
            className={
              "rounded-md px-4 py-1.5 text-sm font-semibold " +
              (state.danger
                ? "bg-danger text-white hover:opacity-90"
                : "bg-accent text-accent-fg hover:opacity-90")
            }
          >
            {state.confirmLabel ?? t("confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}

export function ConfirmHost() {
  const state = useSyncExternalStore(
    subscribe,
    () => current,
    () => null,
  );
  if (!state) return null;
  // Key remounts the body so the prompt input resets per dialog.
  return <DialogBody key={state.message + (state.defaultValue ?? "")} state={state} />;
}
