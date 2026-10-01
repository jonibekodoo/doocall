"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";

import { fetchSalesIntegrator } from "@/lib/api/sales";
import { formatUzs } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUS_TONE: Record<string, string> = {
  active: "bg-accent-soft text-accent",
  trial: "bg-warning/15 text-warning",
  suspended: "bg-danger/10 text-danger",
};

export default function SalesIntegratorDetailPage() {
  const t = useTranslations("sales");
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const { data, isPending } = useQuery({
    queryKey: ["sales-integrator", id],
    queryFn: () => fetchSalesIntegrator(id),
    enabled: Number.isFinite(id),
  });

  if (isPending) return <div className="h-64 animate-pulse rounded-lg bg-surface-2" />;
  if (!data) return null;
  const i = data.integrator;

  return (
    <div data-testid="sales-integrator-detail" className="max-w-3xl">
      <Link href="/sales/integrators" className="mb-4 inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-accent">
        <ArrowLeft className="size-4" /> {t("integrators")}
      </Link>

      <div className="flex items-start gap-4 rounded-2xl border border-border bg-surface p-5">
        <span className="grid size-14 shrink-0 place-items-center overflow-hidden rounded-xl border border-border bg-surface-2 text-lg font-bold text-fg-muted">
          {i.logo_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={i.logo_url} alt="" className="size-full object-contain" />
          ) : (
            (i.company_name || i.name).slice(0, 1).toUpperCase()
          )}
        </span>
        <div className="min-w-0">
          <h1 className="text-xl font-semibold">{i.name}</h1>
          {i.company_name && <p className="text-sm font-medium text-fg-muted">{i.company_name}</p>}
          <p className="mt-1 text-sm text-fg-muted">
            {i.email}{i.phone && <> · {i.phone}</>} · {t("code")}{" "}
            <code className="rounded bg-surface-2 px-1.5">{i.referral_code}</code>
          </p>
          <p className="tnum mt-1 text-sm">
            {t("myCommission")}: <b className="text-accent">{formatUzs(i.my_commission_uzs)} UZS</b>
          </p>
        </div>
      </div>

      <section className="mt-5 rounded-2xl border border-border bg-surface">
        <p className="border-b border-border px-4 py-2.5 text-sm font-semibold">{t("companies")}</p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
              <tr>
                <th className="px-3 py-2 text-left">{t("company")}</th>
                <th className="px-3 py-2 text-left">{t("status")}</th>
                <th className="px-3 py-2 text-right">{t("operators")}</th>
                <th className="px-3 py-2 text-left">{t("created")}</th>
              </tr>
            </thead>
            <tbody>
              {i.companies.map((c) => (
                <tr key={c.id} className="border-t border-border">
                  <td className="px-3 py-2.5 font-medium">{c.name}</td>
                  <td className="px-3 py-2.5">
                    <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", STATUS_TONE[c.status] ?? "bg-surface-3")}>
                      {t(
                        `st_${
                          c.status === "active"
                            ? "active"
                            : c.status === "trial"
                              ? c.trial_ends_at && new Date(c.trial_ends_at) < new Date()
                                ? "expired"
                                : "trial"
                              : "suspended"
                        }`,
                      )}
                    </span>
                  </td>
                  <td className="tnum px-3 py-2.5 text-right">{c.seats}</td>
                  <td className="tnum px-3 py-2.5 text-xs text-fg-faint">{c.created_at.slice(0, 10)}</td>
                </tr>
              ))}
              {i.companies.length === 0 && (
                <tr><td colSpan={4} className="px-4 py-8 text-center text-sm text-fg-faint">—</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
