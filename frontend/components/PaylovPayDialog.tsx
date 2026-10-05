"use client";

/** Paylov one-time card payment (card + expiry → SMS OTP → balance credited).
 * Shared by the license tab and the paywall screen. */

import { useMutation } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { useToastStore } from "@/components/ui/Toast";
import { paylovConfirm, paylovPay } from "@/lib/api/endpoints";
import { fmtCardNumber, fmtExpiryInput, toYYMM } from "@/lib/card";

export function PaylovPayDialog({
  initialAmount,
  onClose,
  onDone,
}: {
  initialAmount: number;
  onClose: () => void;
  onDone: () => void;
}) {
  const t = useTranslations("settings");
  const [step, setStep] = useState<"card" | "otp">("card");
  const [amount, setAmount] = useState(
    initialAmount > 0 ? String(initialAmount) : "",
  );
  const [card, setCard] = useState("");
  const [expiry, setExpiry] = useState("");
  const [otp, setOtp] = useState("");
  const [paymentId, setPaymentId] = useState<number | null>(null);
  const [otpPhone, setOtpPhone] = useState("");

  const cardDigits = card.replace(/\D/g, "");
  const yymm = toYYMM(expiry);
  const canPay =
    Number(amount) >= 1000 &&
    cardDigits.length >= 12 &&
    cardDigits.length <= 19 &&
    yymm !== "";

  const pay = useMutation({
    mutationFn: () => paylovPay(Number(amount), cardDigits, yymm),
    onSuccess: (res) => {
      setPaymentId(res.payment_id);
      setOtpPhone(res.otp_phone);
      setStep("otp");
    },
    onError: (e: Error) =>
      useToastStore.getState().push({ kind: "error", text: e.message }),
  });
  const confirm = useMutation({
    mutationFn: () => paylovConfirm(paymentId as number, otp.trim()),
    onSuccess: onDone,
    onError: (e: Error) =>
      useToastStore.getState().push({ kind: "error", text: e.message }),
  });

  return (
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-4"
      role="dialog"
    >
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-5 shadow-lg">
        <h2 className="mb-1 text-base font-semibold">Paylov</h2>
        {step === "card" ? (
          <>
            <p className="mb-3 text-xs text-fg-muted">{t("paylovCardNote")}</p>
            <label className="mb-2 block text-sm">
              <span className="mb-1 block text-xs text-fg-muted">
                {t("payAmount")}
              </span>
              <input
                type="number"
                min={1000}
                step={1000}
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="tnum w-full rounded-md border border-border bg-surface px-3 py-2"
              />
            </label>
            <label className="mb-2 block text-sm">
              <span className="mb-1 block text-xs text-fg-muted">
                {t("paylovCard")}
              </span>
              <input
                inputMode="numeric"
                placeholder="8600 0000 0000 0000"
                value={fmtCardNumber(card)}
                onChange={(e) => setCard(e.target.value)}
                className="tnum w-full rounded-md border border-border bg-surface px-3 py-2"
              />
            </label>
            <label className="mb-2 block text-sm">
              <span className="mb-1 block text-xs text-fg-muted">
                {t("paylovExpiry")}
              </span>
              <input
                inputMode="numeric"
                placeholder="MM/YY"
                value={fmtExpiryInput(expiry)}
                onChange={(e) => setExpiry(e.target.value)}
                className="tnum w-full rounded-md border border-border bg-surface px-3 py-2"
              />
            </label>
            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-border px-3 py-1.5 text-sm"
              >
                {t("payCancel")}
              </button>
              <button
                type="button"
                disabled={!canPay || pay.isPending}
                onClick={() => pay.mutate()}
                className="rounded-md bg-accent px-4 py-1.5 text-sm font-semibold text-accent-fg disabled:opacity-40"
              >
                {pay.isPending ? "…" : t("paylovGetOtp")}
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="mb-3 text-xs text-fg-muted">
              {t("paylovOtpNote", { phone: otpPhone || "" })}
            </p>
            <label className="mb-2 block text-sm">
              <span className="mb-1 block text-xs text-fg-muted">
                {t("paylovOtp")}
              </span>
              <input
                inputMode="numeric"
                autoFocus
                value={otp}
                onChange={(e) =>
                  setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))
                }
                className="tnum w-full rounded-md border border-border bg-surface px-3 py-2 text-center text-lg tracking-widest"
              />
            </label>
            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-border px-3 py-1.5 text-sm"
              >
                {t("payCancel")}
              </button>
              <button
                type="button"
                disabled={otp.length < 4 || confirm.isPending}
                onClick={() => confirm.mutate()}
                className="rounded-md bg-accent px-4 py-1.5 text-sm font-semibold text-accent-fg disabled:opacity-40"
              >
                {confirm.isPending ? "…" : t("paylovConfirm")}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
