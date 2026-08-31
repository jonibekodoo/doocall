"use client";

/** §6.6 Мои звонки — operator-scoped calls table WITHOUT admin actions. */

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { DirectionIcon } from "@/components/calls-shared";
import { CallAudioButton } from "@/components/CallAudioButton";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { fetchCalls } from "@/lib/api/endpoints";
import type { CallRow } from "@/lib/api/types";
import { formatDuration, formatPhone } from "@/lib/format";

export default function MyCallsPage() {
  const t = useTranslations("calls");
  const tTitle = useTranslations("myCalls");
  const tc = useTranslations("common");
  const [page, setPage] = useState(1);

  // Operator scope: the backend scopes by company; web admins see all, an
  // operator's own web login sees their operator via the employees filter
  // (wired once operator web accounts land). No delete/export here.
  const { data, isPending } = useQuery({
    queryKey: ["my-calls", page],
    queryFn: () => fetchCalls({ page }),
  });

  const columns: Column<CallRow>[] = [
    {
      key: "date",
      header: t("date"),
      cell: (row) => (
        <span className="tnum text-xs">
          {new Date(row.start_time).toLocaleString("ru-RU", {
            day: "2-digit",
            month: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
      ),
    },
    {
      key: "direction",
      header: t("direction"),
      cell: (row) => <DirectionIcon direction={row.direction} />,
    },
    {
      key: "client",
      header: t("client"),
      cell: (row) =>
        row.counterparty_name ?? (
          <span className="tnum">{formatPhone(row.counterparty_number)}</span>
        ),
    },
    {
      key: "duration",
      header: t("duration"),
      numeric: true,
      cell: (row) => formatDuration(row.duration),
    },
    {
      key: "audio",
      header: "▶",
      cell: (row) =>
        row.status === "answered" ? <CallAudioButton callId={row.id} /> : null,
    },
  ];

  const total = data?.count ?? 0;
  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">{tTitle("title")}</h1>
      <DataTable<CallRow>
        columns={columns}
        rows={data?.results ?? []}
        loading={isPending}
        storageKey="my-calls"
      />
      <div className="mt-3 flex items-center justify-between text-sm text-fg-muted">
        <span className="tnum">
          {total === 0 ? 0 : (page - 1) * 30 + 1}—{Math.min(page * 30, total)}{" "}
          {tc("of")} {total}
        </span>
        <div className="flex gap-1.5">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((value) => value - 1)}
            className="rounded-md border border-border px-3 py-1.5 disabled:opacity-40"
          >
            ←
          </button>
          <button
            type="button"
            disabled={data ? page >= data.pages : true}
            onClick={() => setPage((value) => value + 1)}
            className="rounded-md border border-border px-3 py-1.5 disabled:opacity-40"
          >
            →
          </button>
        </div>
      </div>
    </div>
  );
}
