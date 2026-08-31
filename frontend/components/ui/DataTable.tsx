"use client";

/** Shared DataTable: sticky header, skeleton rows, density toggle,
 * empty-state slot, column visibility persisted per user (localStorage key,
 * later synced with /calls/columns). */

import { Columns3, Rows3 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

export interface Column<Row> {
  key: string;
  header: React.ReactNode;
  cell: (row: Row) => React.ReactNode;
  className?: string;
  /** Right-align + tabular numerals (durations, money). */
  numeric?: boolean;
}

export function DataTable<Row extends { id: number | string }>({
  columns,
  rows,
  loading = false,
  skeletonRows = 8,
  empty,
  storageKey,
}: {
  columns: Column<Row>[];
  rows: Row[];
  loading?: boolean;
  skeletonRows?: number;
  empty?: React.ReactNode;
  storageKey?: string;
}) {
  const t = useTranslations("table");
  const [dense, setDense] = useState(false);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [columnsOpen, setColumnsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!storageKey) return;
    try {
      const saved = JSON.parse(
        localStorage.getItem(`cols:${storageKey}`) ?? "[]",
      );
      if (Array.isArray(saved)) setHidden(new Set(saved));
    } catch {
      /* corrupted prefs → defaults */
    }
  }, [storageKey]);

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node))
        setColumnsOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const toggleColumn = (key: string) => {
    setHidden((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      if (storageKey)
        localStorage.setItem(`cols:${storageKey}`, JSON.stringify([...next]));
      return next;
    });
  };

  const visible = columns.filter((column) => !hidden.has(column.key));
  const cellPad = dense ? "px-3 py-1.5" : "px-3 py-2.5";

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface">
      {/* Toolbar */}
      <div className="flex items-center justify-end gap-1 border-b border-border px-2 py-1.5">
        <button
          type="button"
          onClick={() => setDense((value) => !value)}
          aria-label={t("density")}
          aria-pressed={dense}
          className="grid size-7 place-items-center rounded text-fg-faint hover:bg-surface-2 hover:text-fg"
        >
          <Rows3 className="size-4" />
        </button>
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setColumnsOpen((open) => !open)}
            aria-label={t("columns")}
            className="grid size-7 place-items-center rounded text-fg-faint hover:bg-surface-2 hover:text-fg"
          >
            <Columns3 className="size-4" />
          </button>
          {columnsOpen && (
            <div className="absolute right-0 z-10 mt-1 w-44 rounded-md border border-border bg-surface p-1 shadow-lg">
              {columns.map((column) => (
                <label
                  key={column.key}
                  className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-surface-2"
                >
                  <input
                    type="checkbox"
                    checked={!hidden.has(column.key)}
                    onChange={() => toggleColumn(column.key)}
                    className="accent-[var(--accent)]"
                  />
                  {column.header}
                </label>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="panel-scroll max-h-[70vh] overflow-auto">
        <table className="w-full border-collapse text-sm">
          <thead className="sticky top-0 z-[1] bg-surface-2">
            <tr>
              {visible.map((column) => (
                <th
                  key={column.key}
                  className={cn(
                    "border-b border-border text-left text-xs font-semibold uppercase tracking-wide text-fg-muted",
                    cellPad,
                    column.numeric && "text-right",
                    column.className,
                  )}
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: skeletonRows }).map((_, index) => (
                  <tr key={index} data-testid="skeleton-row">
                    {visible.map((column) => (
                      <td key={column.key} className={cellPad}>
                        <div className="h-3.5 animate-pulse rounded bg-surface-3" />
                      </td>
                    ))}
                  </tr>
                ))
              : rows.map((row) => (
                  <tr
                    key={row.id}
                    className="border-b border-border last:border-0 hover:bg-surface-2/60"
                  >
                    {visible.map((column) => (
                      <td
                        key={column.key}
                        className={cn(
                          cellPad,
                          column.numeric && "tnum text-right",
                          column.className,
                        )}
                      >
                        {column.cell(row)}
                      </td>
                    ))}
                  </tr>
                ))}
          </tbody>
        </table>
        {!loading && rows.length === 0 && (
          <div
            data-testid="table-empty"
            className="grid place-items-center px-4 py-16 text-center"
          >
            {empty ?? <p className="text-sm text-fg-faint">{t("empty")}</p>}
          </div>
        )}
      </div>
    </div>
  );
}
