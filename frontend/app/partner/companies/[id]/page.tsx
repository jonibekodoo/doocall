"use client";

/** Read-only commercial card — NO operational data anywhere. */

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";

import { fetchPartnerCompany } from "@/lib/api/partner";
import { formatUzs } from "@/lib/format";

export default function PartnerCompanyCard() {
  const t = useTranslations("partner");
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const { data, isPending } = useQuery({
    queryKey: ["p-company", id],
    queryFn: () => fetchPartnerCompany(id),
    enabled: Number.isFinite(id),
  });

  if (isPending)
    return <div className="h-64 animate-pulse rounded-lg bg-surface-2" />;
  if (!data) return null;
  const c = data.company;

  return (
    <div data-testid="partner-company-card">
      <Link
        href="/partner/companies"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-accent"
      >
        <ArrowLeft className="size-4" /> {t("companies")}
      </Link>
      <div className="rounded-lg border border-border bg-surface p-5">
        <h1 className="text-xl font-semibold">{c.name}</h1>
        <p className="mt-1 text-sm text-fg-muted">
          {c.status} · {c.acquired_via} · {t("operators").toLowerCase()}:{" "}
          <b className="tnum">{c.seats}</b>
        </p>
        <p className="tnum mt-2 text-sm">
          {t("accruedFrom")}:{" "}
          <b className="text-accent">{formatUzs(c.my_cashback_uzs)} UZS</b>
        </p>
      </div>
      <section className="mt-5 rounded-lg border border-border bg-surface">
        <p className="border-b border-border px-4 py-2.5 text-sm font-semibold">
          {t("accruals")}
        </p>
        <ul className="divide-y divide-border">
          {c.accruals.map((a) => (
            <li
              key={a.id}
              className="flex items-center gap-2 px-4 py-2 text-sm"
            >
              <span className="tnum flex-1">
                +{formatUzs(a.amount_uzs)} UZS
              </span>
              <span className="tnum text-xs text-fg-faint">{a.percent}%</span>
              <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs">
                {a.status}
              </span>
              <span className="tnum text-xs text-fg-faint">
                {a.created_at.slice(0, 10)}
              </span>
            </li>
          ))}
          {c.accruals.length === 0 && (
            <li className="px-4 py-8 text-center text-sm text-fg-faint">
              {t("noAccruals")}
            </li>
          )}
        </ul>
      </section>
    </div>
  );
}
