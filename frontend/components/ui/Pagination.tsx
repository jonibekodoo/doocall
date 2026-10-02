"use client";

/** Shared pagination for every list view — 20 rows per page.
 *
 * Two flavours:
 *  - `usePagination(rows)` slices an already-loaded array client-side
 *    (most portal lists are capped at a few hundred rows by the backend);
 *  - `<Pagination>` is the control itself and also works for server-paged
 *    endpoints (calls / contacts) — pass `page`, `pages`, `total`, `onPage`.
 */

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

export const PAGE_SIZE = 20;

export function usePagination<T>(rows: T[], pageSize: number = PAGE_SIZE) {
  const [page, setPage] = useState(1);
  const total = rows.length;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  // A filter/search that shrinks the list must not strand us on a page that
  // no longer exists.
  useEffect(() => {
    if (page > pages) setPage(pages);
  }, [page, pages]);
  const current = Math.min(page, pages);
  const start = total === 0 ? 0 : (current - 1) * pageSize + 1;
  const end = Math.min(current * pageSize, total);
  return {
    page: current,
    pages,
    total,
    start,
    end,
    pageSize,
    slice: rows.slice((current - 1) * pageSize, current * pageSize),
    setPage,
    /** Call when the user changes a filter so they land on page 1 again. */
    reset: () => setPage(1),
  };
}

export function Pagination({
  page,
  pages,
  total,
  start,
  end,
  pageSize = PAGE_SIZE,
  onPage,
  className = "mt-3",
}: {
  page: number;
  pages: number;
  total: number;
  /** Optional explicit range; derived from page/pageSize when omitted. */
  start?: number;
  end?: number;
  pageSize?: number;
  onPage: (page: number) => void;
  className?: string;
}) {
  const tc = useTranslations("common");
  if (total <= 0) return null;
  const from = start ?? (page - 1) * pageSize + 1;
  const to = end ?? Math.min(page * pageSize, total);
  return (
    <div
      className={`flex items-center justify-between gap-3 text-sm text-fg-muted ${className}`}
      data-testid="pagination"
    >
      <span className="tnum" data-testid="pagination-info">
        {from}—{to} {tc("of")} {total}
      </span>
      {pages > 1 && (
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            aria-label="prev"
            disabled={page <= 1}
            onClick={() => onPage(page - 1)}
            className="rounded-md border border-border px-3 py-1.5 disabled:opacity-40"
          >
            ←
          </button>
          <span className="tnum text-xs">
            {page} / {pages}
          </span>
          <button
            type="button"
            aria-label="next"
            disabled={page >= pages}
            onClick={() => onPage(page + 1)}
            className="rounded-md border border-border px-3 py-1.5 disabled:opacity-40"
          >
            →
          </button>
        </div>
      )}
    </div>
  );
}
