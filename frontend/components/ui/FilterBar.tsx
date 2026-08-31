"use client";

import { Search } from "lucide-react";
import { useTranslations } from "next-intl";

/** Horizontal filter strip used above tables; children are filter controls. */
export function FilterBar({
  search,
  onSearch,
  children,
}: {
  search?: string;
  onSearch?: (value: string) => void;
  children?: React.ReactNode;
}) {
  const t = useTranslations("common");
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      {onSearch && (
        <label className="relative min-w-40 flex-1 sm:max-w-64">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-fg-faint" />
          <input
            type="search"
            value={search ?? ""}
            onChange={(event) => onSearch(event.target.value)}
            placeholder={t("search")}
            className="w-full rounded-md border border-border bg-surface py-2 pl-8 pr-3 text-sm placeholder:text-fg-faint"
          />
        </label>
      )}
      {children}
    </div>
  );
}

export function FilterSelect({
  value,
  onChange,
  options,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
  label: string;
}) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="rounded-md border border-border bg-surface px-2.5 py-2 text-sm text-fg"
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
