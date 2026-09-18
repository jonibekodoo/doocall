"use client";

/** "Become an integrator" application form → POST /api/public/integrator-apply.
 * Strings are injected by the server landing page so i18n stays centralised. */

import { Handshake } from "lucide-react";
import { useState } from "react";

interface Strings {
  title: string;
  subtitle: string;
  name: string;
  phone: string;
  email: string;
  company: string;
  message: string;
  submit: string;
  submitting: string;
  success: string;
  error: string;
}

export function IntegratorApplyForm({ strings }: { strings: Strings }) {
  const [form, setForm] = useState({
    full_name: "",
    phone: "",
    email: "",
    company: "",
    message: "",
  });
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">(
    "idle",
  );
  const set =
    (key: keyof typeof form) =>
    (
      e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
    ) =>
      setForm((f) => ({ ...f, [key]: e.target.value }));

  const valid = form.full_name.trim().length >= 2 && form.phone.trim().length >= 5;

  const submit = async () => {
    if (!valid || state === "sending") return;
    setState("sending");
    try {
      const res = await fetch("/api/public/integrator-apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!res.ok) throw new Error("failed");
      setState("done");
      setForm({ full_name: "", phone: "", email: "", company: "", message: "" });
    } catch {
      setState("error");
    }
  };

  return (
    <section id="become-integrator" className="bg-surface-2 py-20">
      <div className="mx-auto max-w-2xl px-6">
        <div className="mb-8 text-center">
          <span className="mx-auto mb-3 grid size-12 place-items-center rounded-xl bg-accent-soft text-accent">
            <Handshake className="size-6" />
          </span>
          <h2 className="font-[family-name:var(--font-display)] text-3xl font-bold sm:text-4xl">
            {strings.title}
          </h2>
          <p className="mt-3 text-fg-muted">{strings.subtitle}</p>
        </div>

        {state === "done" ? (
          <div
            data-testid="apply-success"
            className="rounded-2xl border border-accent/30 bg-accent-soft/50 p-8 text-center"
          >
            <p className="text-lg font-semibold text-accent">
              {strings.success}
            </p>
          </div>
        ) : (
          <div className="rounded-2xl border border-border bg-surface p-6 shadow-lg sm:p-8">
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block text-sm">
                <span className="mb-1 block text-xs font-medium text-fg-muted">
                  {strings.name} *
                </span>
                <input
                  value={form.full_name}
                  onChange={set("full_name")}
                  data-testid="apply-name"
                  className="w-full rounded-md border border-border bg-surface px-3 py-2"
                />
              </label>
              <label className="block text-sm">
                <span className="mb-1 block text-xs font-medium text-fg-muted">
                  {strings.phone} *
                </span>
                <input
                  value={form.phone}
                  onChange={set("phone")}
                  inputMode="tel"
                  placeholder="+998 90 123 45 67"
                  data-testid="apply-phone"
                  className="tnum w-full rounded-md border border-border bg-surface px-3 py-2"
                />
              </label>
              <label className="block text-sm">
                <span className="mb-1 block text-xs font-medium text-fg-muted">
                  {strings.email}
                </span>
                <input
                  value={form.email}
                  onChange={set("email")}
                  inputMode="email"
                  data-testid="apply-email"
                  className="w-full rounded-md border border-border bg-surface px-3 py-2"
                />
              </label>
              <label className="block text-sm">
                <span className="mb-1 block text-xs font-medium text-fg-muted">
                  {strings.company}
                </span>
                <input
                  value={form.company}
                  onChange={set("company")}
                  data-testid="apply-company"
                  className="w-full rounded-md border border-border bg-surface px-3 py-2"
                />
              </label>
            </div>
            <label className="mt-4 block text-sm">
              <span className="mb-1 block text-xs font-medium text-fg-muted">
                {strings.message}
              </span>
              <textarea
                value={form.message}
                onChange={set("message")}
                rows={3}
                data-testid="apply-message"
                className="w-full resize-none rounded-md border border-border bg-surface px-3 py-2"
              />
            </label>

            {state === "error" && (
              <p className="mt-3 text-sm text-danger">{strings.error}</p>
            )}

            <button
              type="button"
              onClick={submit}
              disabled={!valid || state === "sending"}
              data-testid="apply-submit"
              className="mt-5 w-full rounded-md bg-accent px-6 py-3 text-sm font-bold text-accent-fg hover:opacity-90 disabled:opacity-40"
            >
              {state === "sending" ? strings.submitting : strings.submit}
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
