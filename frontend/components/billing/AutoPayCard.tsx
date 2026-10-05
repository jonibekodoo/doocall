"use client";

/** Settings → License: Paylov saved cards + auto-payment.
 *
 * A card is linked once (card + expiry → SMS code); afterwards it can be
 * charged in one click ("Pay now") or automatically when the prepaid balance
 * covers less than one day of service. Turning auto-payment on requires the
 * cardholder's explicit consent. Only company admins may change anything —
 * everyone else sees a read-only summary. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CreditCard, Plus, RefreshCw, Trash2, Zap } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { confirmDialog, promptDialog } from "@/components/ui/Confirm";
import { useToastStore } from "@/components/ui/Toast";
import {
  type AutoPayAmountMode,
  type AutoPayOverview,
  type SavedCard,
  fetchAutoPay,
  linkCardConfirm,
  linkCardStart,
  payWithSavedCard,
  removeSavedCard,
  saveAutoPay,
} from "@/lib/api/endpoints";
import { cardLast4, fmtCardNumber, fmtExpiryInput, fmtYYMM, toYYMM } from "@/lib/card";
import { formatUzs } from "@/lib/format";
import { cn } from "@/lib/utils";

const QUERY_KEY = ["b-autopay"] as const;

const pushError = (error: Error) =>
  useToastStore.getState().push({ kind: "error", text: error.message });

function cardTitle(card: SavedCard): string {
  return `${card.vendor || "Card"} •••• ${cardLast4(card.masked_number)}`;
}

/** Two-step dialog: card + expiry → SMS code. */
function LinkCardDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const t = useTranslations("settings.autopay");
  const [step, setStep] = useState<"card" | "otp">("card");
  const [card, setCard] = useState("");
  const [expiry, setExpiry] = useState("");
  const [otp, setOtp] = useState("");
  const [cardRef, setCardRef] = useState<number | null>(null);
  const [otpPhone, setOtpPhone] = useState("");

  const cardDigits = card.replace(/\D/g, "");
  const yymm = toYYMM(expiry);
  const canStart = cardDigits.length >= 12 && cardDigits.length <= 19 && yymm !== "";

  const start = useMutation({
    mutationFn: () => linkCardStart(cardDigits, yymm),
    onSuccess: (res) => {
      setCardRef(res.card_ref);
      setOtpPhone(res.otp_phone);
      setStep("otp");
    },
    onError: pushError,
  });
  const confirm = useMutation({
    mutationFn: () => linkCardConfirm(cardRef as number, otp.trim()),
    onSuccess: onDone,
    onError: pushError,
  });

  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-4" role="dialog">
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-5 shadow-lg">
        <h2 className="mb-1 text-base font-semibold">{t("linkTitle")}</h2>
        {step === "card" ? (
          <>
            <p className="mb-3 text-xs text-fg-muted">{t("linkNote")}</p>
            <label className="mb-2 block text-sm">
              <span className="mb-1 block text-xs text-fg-muted">{t("cardNumber")}</span>
              <input
                inputMode="numeric"
                autoComplete="off"
                placeholder="8600 0000 0000 0000"
                value={fmtCardNumber(card)}
                onChange={(e) => setCard(e.target.value)}
                data-testid="link-card-number"
                className="tnum w-full rounded-md border border-border bg-surface px-3 py-2"
              />
            </label>
            <label className="mb-2 block text-sm">
              <span className="mb-1 block text-xs text-fg-muted">{t("cardExpiry")}</span>
              <input
                inputMode="numeric"
                autoComplete="off"
                placeholder="MM/YY"
                value={fmtExpiryInput(expiry)}
                onChange={(e) => setExpiry(e.target.value)}
                data-testid="link-card-expiry"
                className="tnum w-full rounded-md border border-border bg-surface px-3 py-2"
              />
            </label>
            <div className="mt-3 flex justify-end gap-2">
              <button type="button" onClick={onClose} className="rounded-md border border-border px-3 py-1.5 text-sm">
                {t("cancel")}
              </button>
              <button
                type="button"
                disabled={!canStart || start.isPending}
                onClick={() => start.mutate()}
                data-testid="link-card-start"
                className="rounded-md bg-accent px-4 py-1.5 text-sm font-semibold text-accent-fg disabled:opacity-40"
              >
                {start.isPending ? "…" : t("getCode")}
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="mb-3 text-xs text-fg-muted">{t("otpNote", { phone: otpPhone || "" })}</p>
            <label className="mb-2 block text-sm">
              <span className="mb-1 block text-xs text-fg-muted">{t("otp")}</span>
              <input
                inputMode="numeric"
                autoFocus
                value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                data-testid="link-card-otp"
                className="tnum w-full rounded-md border border-border bg-surface px-3 py-2 text-center text-lg tracking-widest"
              />
            </label>
            <div className="mt-3 flex justify-end gap-2">
              <button type="button" onClick={onClose} className="rounded-md border border-border px-3 py-1.5 text-sm">
                {t("cancel")}
              </button>
              <button
                type="button"
                disabled={otp.length < 4 || confirm.isPending}
                onClick={() => confirm.mutate()}
                data-testid="link-card-confirm"
                className="rounded-md bg-accent px-4 py-1.5 text-sm font-semibold text-accent-fg disabled:opacity-40"
              >
                {confirm.isPending ? "…" : t("confirmCard")}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Switch({
  checked,
  onChange,
  disabled,
  testId,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  testId?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      data-testid={testId}
      className={cn(
        "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-40",
        checked ? "bg-accent" : "bg-surface-3",
      )}
    >
      <span
        className={cn(
          "inline-block size-5 transform rounded-full bg-white shadow transition-transform",
          checked ? "translate-x-5" : "translate-x-0.5",
        )}
      />
    </button>
  );
}

/** Auto-payment settings form (company admins). */
function AutoPayForm({ data }: { data: AutoPayOverview }) {
  const t = useTranslations("settings.autopay");
  const queryClient = useQueryClient();
  const server = data.autopay;
  const activeCards = data.cards.filter((card) => card.is_active);

  const [enabled, setEnabled] = useState(server.is_enabled);
  const [mode, setMode] = useState<AutoPayAmountMode>(server.amount_mode);
  const [fixed, setFixed] = useState(server.fixed_amount_uzs ? String(server.fixed_amount_uzs) : "");
  const [limit, setLimit] = useState(server.monthly_limit_uzs ? String(server.monthly_limit_uzs) : "");
  const [cardId, setCardId] = useState<number | null>(server.card_id);
  const [consent, setConsent] = useState(false);

  // Re-sync the draft whenever the server state changes (save, card removed…).
  useEffect(() => {
    setEnabled(server.is_enabled);
    setMode(server.amount_mode);
    setFixed(server.fixed_amount_uzs ? String(server.fixed_amount_uzs) : "");
    setLimit(server.monthly_limit_uzs ? String(server.monthly_limit_uzs) : "");
    setCardId(server.card_id);
    setConsent(false);
  }, [
    server.is_enabled,
    server.amount_mode,
    server.fixed_amount_uzs,
    server.monthly_limit_uzs,
    server.card_id,
  ]);

  const chosenCard = cardId ?? activeCards[0]?.id ?? null;
  // Consent is asked every time auto-payment goes from off to on.
  const alreadyAuthorized = server.is_enabled && Boolean(server.consent_at);
  const needsConsent = enabled && !alreadyAuthorized;
  const fixedValid = mode === "month" || Number(fixed) >= 1000;
  const limitValid = limit.trim() === "" || Number(limit) >= 1000;
  const canSave =
    fixedValid &&
    limitValid &&
    (!enabled || (chosenCard !== null && (!needsConsent || consent)));

  const save = useMutation({
    mutationFn: () =>
      saveAutoPay({
        is_enabled: enabled,
        card_id: chosenCard,
        amount_mode: mode,
        fixed_amount_uzs: mode === "fixed" ? Number(fixed) : null,
        monthly_limit_uzs: limit.trim() === "" ? null : Number(limit),
        consent: enabled && (consent || alreadyAuthorized),
      }),
    onSuccess: (body) => {
      queryClient.setQueryData(QUERY_KEY, body);
      useToastStore.getState().push({
        kind: "success",
        text: body.autopay.is_enabled ? t("savedOn") : t("savedOff"),
      });
    },
    onError: pushError,
  });

  return (
    <div className="border-t border-border px-4 py-4" data-testid="autopay-form">
      <div className="flex items-start gap-3">
        <Switch
          checked={enabled}
          onChange={setEnabled}
          disabled={activeCards.length === 0}
          testId="autopay-switch"
        />
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-sm font-semibold">
            <Zap className="size-4 text-accent" /> {t("title")}
          </p>
          <p className="mt-0.5 text-xs text-fg-muted">{t("trigger")}</p>
          {activeCards.length === 0 && (
            <p className="mt-1 text-xs text-warning">{t("needCard")}</p>
          )}
        </div>
      </div>

      {enabled && (
        <div className="mt-4 space-y-3 text-sm">
          {activeCards.length > 1 && (
            <label className="block max-w-xs">
              <span className="mb-1 block text-xs text-fg-muted">{t("chargeCard")}</span>
              <select
                value={chosenCard ?? ""}
                onChange={(e) => setCardId(Number(e.target.value))}
                className="w-full rounded-md border border-border bg-surface px-2.5 py-2 text-sm"
              >
                {activeCards.map((card) => (
                  <option key={card.id} value={card.id}>
                    {cardTitle(card)}
                  </option>
                ))}
              </select>
            </label>
          )}

          <fieldset className="space-y-2">
            <legend className="mb-1 text-xs text-fg-muted">{t("amountLabel")}</legend>
            <label className="flex items-start gap-2">
              <input
                type="radio"
                name="autopay-mode"
                checked={mode === "month"}
                onChange={() => setMode("month")}
                className="mt-0.5 accent-[var(--accent)]"
              />
              <span>{t("modeMonth", { amount: formatUzs(server.default_amount_uzs) })}</span>
            </label>
            <label className="flex flex-wrap items-center gap-2">
              <input
                type="radio"
                name="autopay-mode"
                checked={mode === "fixed"}
                onChange={() => setMode("fixed")}
                className="accent-[var(--accent)]"
              />
              <span>{t("modeFixed")}</span>
              {mode === "fixed" && (
                <span className="flex items-center gap-1.5">
                  <input
                    type="number"
                    min={1000}
                    step={1000}
                    value={fixed}
                    onChange={(e) => setFixed(e.target.value)}
                    data-testid="autopay-fixed"
                    className={cn(
                      "tnum w-36 rounded-md border bg-surface px-2.5 py-1.5",
                      fixedValid ? "border-border" : "border-danger",
                    )}
                  />
                  <span className="text-xs text-fg-muted">UZS</span>
                </span>
              )}
            </label>
          </fieldset>

          <label className="block max-w-xs">
            <span className="mb-1 block text-xs text-fg-muted">{t("limitLabel")}</span>
            <span className="flex items-center gap-1.5">
              <input
                type="number"
                min={1000}
                step={1000}
                value={limit}
                onChange={(e) => setLimit(e.target.value)}
                placeholder={formatUzs(server.effective_limit_uzs)}
                data-testid="autopay-limit"
                className={cn(
                  "tnum w-full rounded-md border bg-surface px-2.5 py-1.5",
                  limitValid ? "border-border" : "border-danger",
                )}
              />
              <span className="text-xs text-fg-muted">UZS</span>
            </span>
            <span className="mt-1 block text-[11px] text-fg-faint">{t("limitHint")}</span>
          </label>

          {needsConsent && (
            <label className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/5 p-3 text-xs leading-relaxed">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
                data-testid="autopay-consent"
                className="mt-0.5 size-4 shrink-0 accent-[var(--accent)]"
              />
              <span>
                {t("consent")}{" "}
                <a href="/legal/terms" target="_blank" rel="noopener noreferrer" className="font-medium text-accent underline">
                  {t("termsLink")}
                </a>
                {" · "}
                <a href="/legal/refund" target="_blank" rel="noopener noreferrer" className="font-medium text-accent underline">
                  {t("refundLink")}
                </a>
              </span>
            </label>
          )}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={!canSave || save.isPending}
          onClick={() => save.mutate()}
          data-testid="autopay-save"
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-fg disabled:opacity-40"
        >
          {save.isPending ? "…" : t("save")}
        </button>
        <span className="tnum text-xs text-fg-muted">
          {t("spent", {
            spent: formatUzs(server.spent_30d_uzs),
            limit: formatUzs(server.effective_limit_uzs),
          })}
        </span>
      </div>
    </div>
  );
}

function StatusLine({ data }: { data: AutoPayOverview }) {
  const t = useTranslations("settings.autopay");
  const state = data.autopay;
  if (!state.last_attempt_at && !state.disabled_reason) return null;
  return (
    <div className="space-y-2 border-t border-border px-4 py-3 text-xs">
      {state.disabled_reason && (
        <p className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-warning" data-testid="autopay-disabled-reason">
          {state.disabled_reason}
        </p>
      )}
      {state.last_attempt_at && (
        <p className="tnum text-fg-muted" data-testid="autopay-last">
          {t("lastAttempt")}: {state.last_attempt_at.slice(0, 16).replace("T", " ")} ·{" "}
          <span
            className={cn(
              "font-semibold",
              state.last_status === "ok" && "text-accent",
              state.last_status === "failed" && "text-danger",
              state.last_status === "pending" && "text-warning",
            )}
          >
            {state.last_status === "ok"
              ? t("statusOk")
              : state.last_status === "failed"
                ? `${t("statusFailed")}${state.last_error ? ` — ${state.last_error}` : ""}`
                : state.last_status === "pending"
                  ? t("statusPending")
                  : "—"}
          </span>
          {state.fail_streak > 0 && ` · ${t("failStreak", { n: state.fail_streak })}`}
        </p>
      )}
    </div>
  );
}

export function AutoPayCard() {
  const t = useTranslations("settings.autopay");
  const queryClient = useQueryClient();
  const [linkOpen, setLinkOpen] = useState(false);
  const { data } = useQuery({ queryKey: QUERY_KEY, queryFn: fetchAutoPay });

  const refreshAll = () => {
    queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    queryClient.invalidateQueries({ queryKey: ["b-overview"] });
    queryClient.invalidateQueries({ queryKey: ["s-license"] });
    queryClient.invalidateQueries({ queryKey: ["notifications"] });
  };

  const remove = useMutation({
    mutationFn: (id: number) => removeSavedCard(id),
    onSuccess: () => {
      refreshAll();
      useToastStore.getState().push({ kind: "success", text: t("cardRemoved") });
    },
    onError: pushError,
  });
  const payNow = useMutation({
    mutationFn: ({ id, amount }: { id: number; amount: number }) => payWithSavedCard(id, amount),
    onSuccess: () => {
      refreshAll();
      useToastStore.getState().push({ kind: "success", text: t("paid") });
    },
    onError: (error: Error) => {
      refreshAll(); // a failed charge still updates the status line
      pushError(error);
    },
  });

  if (!data || !data.available) return null;

  const askPay = async (card: SavedCard) => {
    const raw = await promptDialog(
      t("payPrompt", { card: cardTitle(card) }),
      String(data.autopay.default_amount_uzs || ""),
    );
    if (raw === null) return;
    const amount = Number(raw.replace(/\s/g, ""));
    if (!Number.isFinite(amount) || amount < 1000) {
      useToastStore.getState().push({ kind: "error", text: t("amountInvalid") });
      return;
    }
    payNow.mutate({ id: card.id, amount });
  };

  return (
    <section className="rounded-lg border border-border bg-surface" data-testid="autopay-card">
      {linkOpen && (
        <LinkCardDialog
          onClose={() => setLinkOpen(false)}
          onDone={() => {
            setLinkOpen(false);
            refreshAll();
            useToastStore.getState().push({ kind: "success", text: t("cardLinked") });
          }}
        />
      )}

      <header className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2.5">
        <CreditCard className="size-4 text-accent" />
        <p className="text-sm font-semibold">{t("cardsTitle")}</p>
        {data.autopay.is_enabled && (
          <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-semibold text-accent">
            {t("badgeOn")}
          </span>
        )}
        {data.can_manage && (
          <button
            type="button"
            onClick={() => setLinkOpen(true)}
            data-testid="link-card-btn"
            className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-accent px-3 py-1.5 text-xs font-semibold text-accent hover:bg-accent-soft"
          >
            <Plus className="size-3.5" /> {t("linkCard")}
          </button>
        )}
      </header>

      {data.cards.length === 0 ? (
        <p className="px-4 py-5 text-center text-xs text-fg-faint">{t("noCards")}</p>
      ) : (
        <ul className="divide-y divide-border">
          {data.cards.map((card) => (
            <li key={card.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2.5 text-sm" data-testid={`saved-card-${card.id}`}>
              <span className="grid size-8 shrink-0 place-items-center rounded-md bg-surface-2 text-fg-muted">
                <CreditCard className="size-4" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="tnum block font-medium">
                  {cardTitle(card)}
                  {!card.is_active && (
                    <span className="ml-2 rounded-full bg-danger/10 px-2 py-0.5 text-[11px] font-semibold text-danger">
                      {t("cardInactive")}
                    </span>
                  )}
                  {data.autopay.is_enabled && data.autopay.card_id === card.id && (
                    <span className="ml-2 rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-semibold text-accent">
                      {t("badgeAuto")}
                    </span>
                  )}
                </span>
                <span className="tnum block truncate text-xs text-fg-faint">
                  {[card.owner, fmtYYMM(card.expire)].filter(Boolean).join(" · ")}
                </span>
              </span>
              {data.can_manage && (
                <span className="flex items-center gap-1.5">
                  {card.is_active && (
                    <button
                      type="button"
                      disabled={payNow.isPending}
                      onClick={() => askPay(card)}
                      data-testid={`pay-saved-${card.id}`}
                      className="inline-flex items-center gap-1 rounded-md bg-accent px-2.5 py-1.5 text-xs font-semibold text-accent-fg disabled:opacity-40"
                    >
                      {payNow.isPending ? (
                        <RefreshCw className="size-3.5 animate-spin" />
                      ) : (
                        <Zap className="size-3.5" />
                      )}
                      {t("payNow")}
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={remove.isPending}
                    onClick={async () =>
                      (await confirmDialog(t("removeConfirm", { card: cardTitle(card) }), {
                        danger: true,
                        confirmLabel: t("remove"),
                      })) && remove.mutate(card.id)
                    }
                    aria-label={t("remove")}
                    title={t("remove")}
                    data-testid={`remove-card-${card.id}`}
                    className="grid size-7 place-items-center rounded-md border border-danger/40 text-danger hover:bg-danger/5 disabled:opacity-40"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      {data.can_manage ? (
        <AutoPayForm data={data} />
      ) : (
        <p className="border-t border-border px-4 py-3 text-xs text-fg-muted" data-testid="autopay-readonly">
          {t("title")}:{" "}
          <b className={data.autopay.is_enabled ? "text-accent" : "text-fg"}>
            {data.autopay.is_enabled ? t("on") : t("off")}
          </b>{" "}
          · {t("adminOnly")}
        </p>
      )}

      <StatusLine data={data} />
    </section>
  );
}
