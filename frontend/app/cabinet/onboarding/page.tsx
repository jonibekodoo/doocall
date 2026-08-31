"use client";

/** Post-registration onboarding checklist — dismissible, state-persisted.
 * Steps auto-complete from real data (operators exist / first call arrived). */

import { useQuery } from "@tanstack/react-query";
import { Check, Download, PhoneCall, UserPlus, X } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { fetchCalls, fetchUsers } from "@/lib/api/endpoints";
import { cn } from "@/lib/utils";

const DISMISS_KEY = "doocall_onboarding_dismissed";

export default function OnboardingPage() {
  const t = useTranslations("onboarding");
  const router = useRouter();
  const [apkDownloaded, setApkDownloaded] = useState(false);

  useEffect(() => {
    if (localStorage.getItem(DISMISS_KEY) === "1") router.replace("/cabinet");
    setApkDownloaded(localStorage.getItem("doocall_apk_step") === "1");
  }, [router]);

  const { data: users } = useQuery({
    queryKey: ["s-users"],
    queryFn: fetchUsers,
  });
  const { data: calls } = useQuery({
    queryKey: ["onboarding-calls"],
    queryFn: () => fetchCalls({ page: 1 }),
  });

  const hasOperator = (users?.operators.length ?? 0) > 0;
  const hasCall = (calls?.count ?? 0) > 0;

  const dismiss = () => {
    localStorage.setItem(DISMISS_KEY, "1");
    router.replace("/cabinet");
  };

  const steps = [
    {
      key: "step1",
      done: hasOperator,
      icon: UserPlus,
      href: "/cabinet/settings",
      external: false,
    },
    {
      key: "step2",
      done: apkDownloaded,
      icon: Download,
      href: "#apk-placeholder", // APK link placeholder (real link in Phase 9)
      external: true,
    },
    {
      key: "step3",
      done: hasCall,
      icon: PhoneCall,
      href: "/cabinet/calls",
      external: false,
    },
  ] as const;

  return (
    <div className="mx-auto max-w-xl" data-testid="onboarding">
      <div className="flex items-start justify-between">
        <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold">
          {t("title")}
        </h1>
        <button
          type="button"
          data-testid="onboarding-dismiss"
          onClick={dismiss}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-fg-faint hover:bg-surface-2 hover:text-fg"
        >
          <X className="size-3.5" /> {t("dismiss")}
        </button>
      </div>

      <ol className="mt-6 space-y-3">
        {steps.map((step, index) => (
          <li key={step.key}>
            <Link
              href={step.href}
              onClick={() => {
                if (step.key === "step2") {
                  localStorage.setItem("doocall_apk_step", "1");
                  setApkDownloaded(true);
                }
              }}
              className={cn(
                "flex items-center gap-4 rounded-xl border p-4 transition-colors",
                step.done
                  ? "border-accent/40 bg-accent-soft/40"
                  : "border-border bg-surface hover:bg-surface-2",
              )}
            >
              <span
                className={cn(
                  "grid size-10 shrink-0 place-items-center rounded-full",
                  step.done
                    ? "bg-accent text-accent-fg"
                    : "bg-surface-3 text-fg-muted",
                )}
              >
                {step.done ? (
                  <Check className="size-5" />
                ) : (
                  <step.icon className="size-5" />
                )}
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold">
                  {index + 1}. {t(step.key)}
                  {step.done && (
                    <span className="ml-2 text-xs font-medium text-accent">
                      {t("done")}
                    </span>
                  )}
                </span>
                <span className="block text-xs text-fg-muted">
                  {t(`${step.key}Hint`)}
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </div>
  );
}
