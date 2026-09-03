"use client";

/** Mobile app (APK) releases: upload a new build, list history.
 * The newest build is what the landing "download app" button serves. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Smartphone, Trash2, UploadCloud } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRef, useState } from "react";

import { confirmDialog } from "@/components/ui/Confirm";
import { useToastStore } from "@/components/ui/Toast";
import {
  deleteAppRelease,
  fetchAppReleases,
  uploadAppRelease,
} from "@/lib/api/admin";
import { useAuth } from "@/lib/auth";

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${bytes} B`;
}

export default function AdminAppPage() {
  const t = useTranslations("admin.app");
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isSuper = user?.role === "superadmin";
  const [version, setVersion] = useState("");
  const [notes, setNotes] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const { data, isPending } = useQuery({
    queryKey: ["a-app-releases"],
    queryFn: fetchAppReleases,
  });

  const upload = useMutation({
    mutationFn: () => uploadAppRelease(version.trim(), notes.trim(), file!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["a-app-releases"] });
      useToastStore.getState().push({ kind: "success", text: t("uploaded") });
      setVersion("");
      setNotes("");
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
    },
    onError: (error: Error) =>
      useToastStore.getState().push({ kind: "error", text: error.message }),
  });

  const remove = useMutation({
    mutationFn: (id: number) => deleteAppRelease(id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["a-app-releases"] }),
  });

  const valid = version.trim().length >= 1 && file !== null;

  return (
    <div data-testid="admin-app">
      <h1 className="mb-4 flex items-center gap-2 text-xl font-semibold">
        <Smartphone className="size-5 text-accent" /> {t("title")}
      </h1>

      {/* Upload card */}
      <div className="mb-6 max-w-xl rounded-lg border border-border bg-surface p-4">
        <p className="mb-3 text-sm font-semibold">{t("uploadTitle")}</p>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="mb-1 block text-xs text-fg-muted">
              {t("version")}
            </span>
            <input
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              placeholder="1.2.0"
              data-testid="apk-version"
              className="tnum w-full rounded-md border border-border bg-surface px-3 py-2"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-xs text-fg-muted">
              {t("notes")}
            </span>
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              data-testid="apk-notes"
              className="w-full rounded-md border border-border bg-surface px-3 py-2"
            />
          </label>
        </div>
        <label className="mt-2 block text-sm">
          <span className="mb-1 block text-xs text-fg-muted">
            {t("fileLabel")}
          </span>
          <input
            ref={fileRef}
            type="file"
            accept=".apk"
            data-testid="apk-file"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-accent-soft file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-accent"
          />
        </label>
        <button
          type="button"
          data-testid="apk-upload"
          disabled={!valid || upload.isPending}
          onClick={() => upload.mutate()}
          className="mt-3 inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-fg disabled:opacity-40"
        >
          <UploadCloud className="size-4" />
          {upload.isPending ? "…" : t("upload")}
        </button>
      </div>

      {/* History */}
      <div className="overflow-hidden rounded-lg border border-border bg-surface">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
            <tr>
              <th className="px-3 py-2 text-left">{t("version")}</th>
              <th className="px-3 py-2 text-right">{t("size")}</th>
              <th className="px-3 py-2 text-left">{t("notes")}</th>
              <th className="px-3 py-2 text-left">{t("uploadedBy")}</th>
              <th className="px-3 py-2 text-left">{t("date")}</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody data-testid="apk-list">
            {isPending ? (
              <tr>
                <td colSpan={6} className="px-3 py-6">
                  <div className="h-4 animate-pulse rounded bg-surface-2" />
                </td>
              </tr>
            ) : (
              (data?.releases ?? []).map((release, index) => (
                <tr key={release.id} className="border-t border-border">
                  <td className="tnum px-3 py-2 font-medium">
                    {release.version}
                    {index === 0 && (
                      <span className="ml-2 rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-bold uppercase text-accent">
                        {t("current")}
                      </span>
                    )}
                  </td>
                  <td className="tnum px-3 py-2 text-right">
                    {formatSize(release.size_bytes)}
                  </td>
                  <td className="px-3 py-2 text-fg-muted">{release.notes}</td>
                  <td className="px-3 py-2 text-xs text-fg-muted">
                    {release.uploaded_by ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-xs text-fg-muted">
                    {new Date(release.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {isSuper && (
                      <button
                        type="button"
                        aria-label={t("delete")}
                        onClick={async () =>
                          (await confirmDialog(t("deleteConfirm"), {
                            danger: true,
                          })) && remove.mutate(release.id)
                        }
                        className="grid size-7 place-items-center rounded-md text-fg-faint hover:bg-danger/10 hover:text-danger"
                      >
                        <Trash2 className="size-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
            {!isPending && (data?.releases ?? []).length === 0 && (
              <tr>
                <td
                  colSpan={6}
                  className="px-3 py-8 text-center text-xs text-fg-faint"
                >
                  {t("empty")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
