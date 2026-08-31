"use client";

/** Minimal toast system (no external dep): store + portal renderer. */

import {
  createContext,
  useContext,
  useEffect,
  useSyncExternalStore,
} from "react";

export interface Toast {
  id: number;
  kind: "error" | "success" | "info";
  text: string;
}

type Listener = () => void;

let toasts: Toast[] = [];
let nextId = 1;
const listeners = new Set<Listener>();

function emit() {
  for (const listener of listeners) listener();
}

export const useToastStore = {
  getState: () => ({
    push(toast: Omit<Toast, "id">) {
      toasts = [...toasts, { ...toast, id: nextId++ }];
      emit();
    },
    dismiss(id: number) {
      toasts = toasts.filter((t) => t.id !== id);
      emit();
    },
  }),
};

function useToasts(): Toast[] {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => toasts,
    () => toasts,
  );
}

const ToastContext = createContext<null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  return (
    <ToastContext.Provider value={null}>
      {children}
      <ToastViewport />
    </ToastContext.Provider>
  );
}

function ToastViewport() {
  const items = useToasts();
  return (
    <div className="fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
      {items.map((toast) => (
        <ToastItem key={toast.id} toast={toast} />
      ))}
    </div>
  );
}

function ToastItem({ toast }: { toast: Toast }) {
  const { dismiss } = useToastStore.getState();
  useEffect(() => {
    const timer = setTimeout(() => dismiss(toast.id), 5000);
    return () => clearTimeout(timer);
  }, [toast.id, dismiss]);

  const tone =
    toast.kind === "error"
      ? "border-danger/40 bg-surface text-danger-strong"
      : "border-border bg-surface text-fg";
  return (
    <button
      type="button"
      role="status"
      onClick={() => dismiss(toast.id)}
      className={`rounded-md border px-4 py-3 text-left text-sm shadow-lg ${tone}`}
    >
      {toast.text}
    </button>
  );
}

export function useToastContext() {
  return useContext(ToastContext);
}
