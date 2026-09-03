"use client";

/** CRM catalog manager: the logo tiles every company sees in its cabinet
 * integration grid (name + site link + logo, moizvonki-style). */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRef, useState } from "react";

import { confirmDialog } from "@/components/ui/Confirm";
import { useToastStore } from "@/components/ui/Toast";
import {
  createCrmCatalogEntry,
  deleteCrmCatalogEntry,
  fetchCrmCatalogAdmin,
  updateCrmCatalogEntry,
} from "@/lib/api/admin";
import { cn } from "@/lib/utils";

export default function AdminCrmCatalogPage() {
  const t = useTranslations("admin.crmCatalog");
  const queryClient = useQueryClient();
  const { data, isPending } = useQuery({
    queryKey: ["a-crm-catalog"],
    queryFn: fetchCrmCatalogAdmin,
  });
  const [name, setName] = useState("");
  const [siteUrl, setSiteUrl] = useState("");
  const [sortOrder, setSortOrder] = useState("100");
  const [logo, setLogo] = useState<File | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["a-crm-catalog"] });

  const create = useMutation({
    mutationFn: () =>
      createCrmCatalogEntry({
        name: name.trim(),
        site_url: siteUrl.trim(),
        sort_order: Number(sortOrder) || 100,
        logo,
      }),
    onSuccess: () => {
      setName("");
      setSiteUrl("");
      setSortOrder("100");
      setLogo(null);
      if (fileInput.current) fileInput.current.value = "";
      invalidate();
      useToastStore.getState().push({ kind: "success", text: t("added") });
    },
    onError: (error: Error) =>
      useToastStore.getState().push({ kind: "error", text: error.message }),
  });

  const toggle = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      updateCrmCatalogEntry(id, { is_active: active }),
    onSuccess: invalidate,
  });

  const destroy = useMutation({
    mutationFn: (id: number) => deleteCrmCatalogEntry(id),
    onSuccess: invalidate,
  });

  const valid = name.trim().length >= 2 && siteUrl.trim().startsWith("http");

  return (
    <div data-testid="admin-crm-catalog">
      <h1 className="mb-1 text-xl font-semibold">{t("title")}</h1>
      <p className="mb-4 text-sm text-fg-muted">{t("subtitle")}</p>

      <div className="mb-5 rounded-lg border border-border bg-surface p-4">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block text-sm">
            <span className="mb-1 block text-xs text-fg-muted">
              {t("name")} *
            </span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="EnvyCRM"
              data-testid="catalog-name"
              className="w-full rounded-md border border-border bg-surface px-3 py-2"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-xs text-fg-muted">
              {t("siteUrl")} *
            </span>
            <input
              value={siteUrl}
              onChange={(event) => setSiteUrl(event.target.value)}
              placeholder="https://envycrm.com"
              data-testid="catalog-url"
              className="w-full rounded-md border border-border bg-surface px-3 py-2"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-xs text-fg-muted">
              {t("logo")}
            </span>
            <input
              ref={fileInput}
              type="file"
              accept="image/png,image/jpeg,image/svg+xml,image/webp"
              onChange={(event) => setLogo(event.target.files?.[0] ?? null)}
              className="w-full text-xs"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-xs text-fg-muted">
              {t("sortOrder")}
            </span>
            <input
              type="number"
              value={sortOrder}
              onChange={(event) => setSortOrder(event.target.value)}
              className="tnum w-full rounded-md border border-border bg-surface px-3 py-2"
            />
          </label>
        </div>
        <button
          type="button"
          data-testid="catalog-add"
          disabled={!valid || create.isPending}
          onClick={() => create.mutate()}
          className="mt-3 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-fg disabled:opacity-50"
        >
          {t("add")}
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {isPending && (
          <div className="h-28 animate-pulse rounded-lg bg-surface-2" />
        )}
        {(data?.entries ?? []).map((entry) => (
          <div
            key={entry.id}
            className={cn(
              "rounded-lg border border-border bg-surface p-3",
              !entry.is_active && "opacity-50",
            )}
          >
            <div className="grid h-16 place-items-center">
              {entry.logo_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={entry.logo_url}
                  alt={entry.name}
                  className="max-h-14 max-w-full object-contain"
                />
              ) : (
                <span className="text-sm font-semibold text-fg-muted">
                  {entry.name}
                </span>
              )}
            </div>
            <p className="mt-2 truncate text-center text-xs text-fg-muted">
              {entry.name} ·{" "}
              <a
                href={entry.site_url}
                target="_blank"
                rel="noreferrer noopener"
                className="text-accent hover:underline"
              >
                {t("site")}
              </a>
            </p>
            <div className="mt-2 flex items-center justify-center gap-2">
              <button
                type="button"
                onClick={() =>
                  toggle.mutate({ id: entry.id, active: !entry.is_active })
                }
                className="rounded-md border border-border px-2 py-1 text-xs"
              >
                {entry.is_active ? t("hide") : t("show")}
              </button>
              <button
                type="button"
                aria-label={`delete ${entry.name}`}
                onClick={async () =>
                  (await confirmDialog(t("deleteConfirm", { name: entry.name }), {
                    danger: true,
                  })) && destroy.mutate(entry.id)
                }
                className="grid size-7 place-items-center rounded-md text-fg-muted hover:bg-danger/10 hover:text-danger"
              >
                <Trash2 className="size-3.5" />
              </button>
            </div>
          </div>
        ))}
        {data && data.entries.length === 0 && (
          <p className="col-span-full rounded-lg border border-border bg-surface p-8 text-center text-sm text-fg-faint">
            {t("empty")}
          </p>
        )}
      </div>
    </div>
  );
}
