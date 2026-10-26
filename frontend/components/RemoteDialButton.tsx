"use client";

/** Remote Dial: ask an operator's phone (DooCall app) to call a number, then
 * follow the command live (poll every second until a final state / ~60 s).
 * Renders nothing when the user has no dial-capable devices. */

import { useQuery } from "@tanstack/react-query";
import { Loader2, Phone, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "@/lib/api/client";
import {
  fetchDialCommand,
  fetchDialDevices,
  startDial,
} from "@/lib/api/endpoints";
import type { DialCommandState, DialDevice, DialStatus } from "@/lib/api/types";
import { formatDuration, formatPhone } from "@/lib/format";
import { cn } from "@/lib/utils";

const FINAL: DialStatus[] = [
  "rejected",
  "disconnected",
  "failed",
  "expired",
  "offline",
];
const KNOWN: DialStatus[] = ["sent", "received", "dialing", "active", ...FINAL];
const POLL_MS = 1000;
// The phone acks only after the operator confirms (up to 30 s) → wait longer.
const POLL_LIMIT_MS = 75_000;
/** Still "sent" after this long → the operator is being asked to confirm. */
const AWAIT_CONFIRM_MS = 3_000;
const REJECT_REASONS = [
  "permission_denied",
  "invalid_number",
  "another_call_active",
  "sim_disabled",
  "duplicate",
  "feature_disabled",
  "user_declined",
  "timeout",
  "expired",
  "rate_limited",
] as const;

/** Shared, cached device list (one request for every button on the page). */
export function useDialDevices() {
  return useQuery({
    queryKey: ["dial-devices"],
    queryFn: fetchDialDevices,
    staleTime: 60_000,
    retry: false,
  });
}

/** Typed number → what we send: formatting (spaces, -, ., brackets) is
 * dropped; the rest must be an optional "+" and 7–15 digits. */
export function normalizeDialNumber(raw: string): {
  value: string;
  valid: boolean;
} {
  const value = raw.trim().replace(/[\s\-.()]/g, "");
  return { value, valid: /^\+?\d{7,15}$/.test(value) };
}

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function deviceLabel(device: DialDevice): string {
  return [device.operator?.full_name, device.model].filter(Boolean).join(" · ");
}

/** One human line for the current command state. */
function useStatusText() {
  const t = useTranslations("dial");
  return (state: DialCommandState): string => {
    switch (state.status) {
      case "sent":
        return t("st_sent");
      case "received": {
        const sim =
          state.sim_mode === "ask"
            ? t("simAsk")
            : typeof state.used_sim_slot === "number"
              ? t("simSlot", { n: state.used_sim_slot + 1 })
              : "";
        return sim ? t("st_receivedSim", { sim }) : t("st_received");
      }
      case "dialing":
        return t("st_dialing");
      case "active":
        return t("st_active");
      case "disconnected": {
        const parts = [
          typeof state.duration_sec === "number"
            ? formatDuration(state.duration_sec)
            : "",
          state.cause ?? "",
        ].filter(Boolean);
        return parts.length
          ? t("st_disconnectedInfo", { info: parts.join(", ") })
          : t("st_disconnected");
      }
      case "rejected": {
        const reason = state.reject_reason ?? "";
        return (REJECT_REASONS as readonly string[]).includes(reason)
          ? t(`reject_${reason as (typeof REJECT_REASONS)[number]}`)
          : t("reject_other");
      }
      case "failed":
        return state.cause
          ? t("st_failedCause", { cause: state.cause })
          : t("st_failed");
      case "expired":
        return t("st_expired");
      case "offline":
        return t("st_offline");
      default:
        // Unknown/missing status: never print it — the phone hasn't answered.
        return t("st_sent");
    }
  };
}

function DialModal({
  number,
  devices,
  onClose,
}: {
  number: string;
  devices: DialDevice[];
  onClose: () => void;
}) {
  const t = useTranslations("dial");
  const statusText = useStatusText();
  const online = devices.filter((device) => device.online);
  const [target, setTarget] = useState(formatPhone(number));
  const [deviceId, setDeviceId] = useState(
    online.length === 1 ? online[0].device_id : "",
  );
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [commandId, setCommandId] = useState<string | null>(null);
  const [initial, setInitial] = useState<DialCommandState | null>(null);
  const startedAt = useRef(0);

  const { data: polled } = useQuery({
    queryKey: ["dial-command", commandId],
    queryFn: () => fetchDialCommand(commandId!),
    enabled: commandId !== null && !FINAL.includes(initial?.status ?? "sent"),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status && FINAL.includes(status)) return false;
      if (Date.now() - startedAt.current > POLL_LIMIT_MS) return false;
      return POLL_MS;
    },
    retry: false,
  });
  const raw: DialCommandState | null = polled ?? initial;
  // A missing/unknown status reads as "sent" (still waiting, keep polling).
  const state: DialCommandState | null = raw
    ? { ...raw, status: KNOWN.includes(raw.status) ? raw.status : "sent" }
    : null;
  const final = state ? FINAL.includes(state.status) : false;

  const [timedOut, setTimedOut] = useState(false);
  useEffect(() => {
    if (!commandId || final) return;
    const timer = setTimeout(() => setTimedOut(true), POLL_LIMIT_MS);
    return () => clearTimeout(timer);
  }, [commandId, final]);

  const [awaitingConfirm, setAwaitingConfirm] = useState(false);
  useEffect(() => {
    if (!commandId || state?.status !== "sent") return;
    const timer = setTimeout(() => setAwaitingConfirm(true), AWAIT_CONFIRM_MS);
    return () => clearTimeout(timer);
  }, [commandId, state?.status]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const dialNumber = normalizeDialNumber(target);

  const dial = async () => {
    if (!deviceId || pending || !dialNumber.valid) return;
    setPending(true);
    setError(null);
    setTimedOut(false);
    startedAt.current = Date.now();
    try {
      const body = await startDial({
        device_id: deviceId,
        number: dialNumber.value,
        idempotency_key: newIdempotencyKey(),
      });
      setInitial({ status: body.status ?? "sent" });
      setCommandId(body.command_id);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        // Device offline: still a command, final state "offline".
        const body = (caught.body ?? {}) as { command_id?: string };
        setInitial({ status: "offline" });
        setCommandId(body.command_id ?? null);
      } else if (caught instanceof ApiError && caught.status === 429) {
        setError(t("rateLimited"));
      } else if (caught instanceof ApiError && caught.status === 400) {
        // Backend validation text verbatim (invalid number, blocked route…).
        const message = (caught.body as { message?: string } | null)?.message;
        setError(message || t("failedToStart"));
      } else {
        setError(caught instanceof Error ? caught.message : t("failedToStart"));
      }
    } finally {
      setPending(false);
    }
  };

  const restart = () => {
    setCommandId(null);
    setInitial(null);
    setTimedOut(false);
    setAwaitingConfirm(false);
  };

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4"
      role="dialog"
      aria-label={t("title")}
      data-testid="dial-modal"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div className="w-full max-w-md space-y-4 rounded-xl border border-border bg-surface p-5 shadow-xl">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-base font-semibold">
            <Phone className="size-4 text-accent" /> {t("title")}
          </h2>
          <button
            type="button"
            aria-label={t("close")}
            data-testid="dial-close"
            onClick={onClose}
            className="grid size-8 place-items-center rounded-md hover:bg-surface-2"
          >
            <X className="size-4" />
          </button>
        </div>

        {state === null ? (
          <>
            <label className="block text-sm">
              <span className="mb-1 block text-xs text-fg-muted">
                {t("number")}
              </span>
              <input
                value={target}
                onChange={(event) => setTarget(event.target.value)}
                inputMode="tel"
                data-testid="dial-number"
                aria-invalid={!dialNumber.valid}
                className={cn(
                  "tnum w-full rounded-md border bg-surface px-3 py-2 text-sm",
                  dialNumber.valid ? "border-border" : "border-danger",
                )}
              />
              {!dialNumber.valid && (
                <span
                  data-testid="dial-number-hint"
                  className="mt-1 block text-xs text-danger"
                >
                  {t("numberHint")}
                </span>
              )}
            </label>
            <div className="text-sm">
              <span className="mb-1 block text-xs text-fg-muted">
                {t("device")}
              </span>
              <div
                className="space-y-1"
                role="radiogroup"
                aria-label={t("device")}
              >
                {devices.map((device) => (
                  <label
                    key={device.device_id}
                    data-testid={`dial-device-${device.device_id}`}
                    className={cn(
                      "flex items-center gap-2 rounded-md border border-border px-3 py-2",
                      device.online
                        ? "cursor-pointer hover:bg-surface-2"
                        : "cursor-not-allowed opacity-60",
                      deviceId === device.device_id &&
                        "border-accent bg-accent-soft/40",
                    )}
                  >
                    <input
                      type="radio"
                      name="dial-device"
                      value={device.device_id}
                      checked={deviceId === device.device_id}
                      disabled={!device.online}
                      onChange={() => setDeviceId(device.device_id)}
                      className="accent-[var(--accent)]"
                    />
                    <span
                      aria-hidden
                      className={cn(
                        "size-2 shrink-0 rounded-full",
                        device.online ? "bg-accent" : "bg-fg-faint",
                      )}
                    />
                    <span className="min-w-0 flex-1 truncate">
                      {deviceLabel(device)}
                    </span>
                    <span className="text-xs text-fg-faint">
                      {device.online ? t("online") : t("offline")}
                    </span>
                  </label>
                ))}
              </div>
              {online.length === 0 && (
                <p className="mt-2 text-xs text-warning">{t("noOnline")}</p>
              )}
            </div>
            {error && (
              <p
                role="alert"
                data-testid="dial-error"
                className="text-sm text-danger"
              >
                {error}
              </p>
            )}
            <button
              type="button"
              data-testid="dial-start"
              disabled={!deviceId || pending || !dialNumber.valid}
              onClick={dial}
              className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-fg disabled:opacity-50"
            >
              {pending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Phone className="size-4" />
              )}
              {t("call")}
            </button>
          </>
        ) : (
          <div className="space-y-3">
            <p className="tnum text-sm text-fg-muted">{target}</p>
            <p
              data-testid="dial-status"
              data-status={state.status}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium",
                state.status === "rejected" ||
                  state.status === "failed" ||
                  state.status === "expired" ||
                  state.status === "offline"
                  ? "bg-danger/10 text-danger"
                  : "bg-accent-soft text-accent",
              )}
            >
              {!final && !timedOut && (
                <Loader2 className="size-4 animate-spin" />
              )}
              {state.status === "sent" && awaitingConfirm
                ? t("st_awaitingConfirm")
                : statusText(state)}
            </p>
            {state.status === "received" && (
              <p
                data-testid="dial-confirm-note"
                className="text-xs font-medium text-fg-muted"
              >
                {t("confirmOnPhone")}
              </p>
            )}
            {timedOut && !final && (
              <p data-testid="dial-timeout" className="text-xs text-fg-muted">
                {t("pollStopped")}
              </p>
            )}
            <p className="text-xs leading-relaxed text-fg-faint">{t("note")}</p>
            <div className="flex gap-2">
              {(final || timedOut) && (
                <button
                  type="button"
                  data-testid="dial-again"
                  onClick={restart}
                  className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-surface-2"
                >
                  {t("again")}
                </button>
              )}
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-surface-2"
              >
                {t("close")}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** Phone icon next to a number; hidden when there is nothing to dial with. */
export function RemoteDialButton({ number }: { number: string }) {
  const t = useTranslations("dial");
  const { data: devices } = useDialDevices();
  const [open, setOpen] = useState(false);
  const list = useMemo(() => devices ?? [], [devices]);
  if (!number || list.length === 0) return null;
  return (
    <>
      <button
        type="button"
        data-testid="remote-dial"
        title={t("title")}
        aria-label={t("title")}
        onClick={() => setOpen(true)}
        className="grid size-6 shrink-0 place-items-center rounded-full text-fg-faint hover:bg-accent-soft hover:text-accent"
      >
        <Phone className="size-3.5" />
      </button>
      {open && (
        <DialModal
          number={number}
          devices={list}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
