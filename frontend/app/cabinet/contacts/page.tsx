"use client";

/** §6.3 Контакты — list + create/edit dialogs (zod) + from-call prefill. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Contact2, Pencil, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { z } from "zod";

import { DataTable, type Column } from "@/components/ui/DataTable";
import { FilterBar } from "@/components/ui/FilterBar";
import { confirmDialog } from "@/components/ui/Confirm";
import { useToastStore } from "@/components/ui/Toast";
import {
  contactFromCall,
  createContact,
  deleteContact,
  fetchCallDetail,
  fetchContacts,
  updateContact,
} from "@/lib/api/endpoints";
import type { ContactRow } from "@/lib/api/types";
import { formatPhone } from "@/lib/format";

const contactSchema = z.object({
  name: z.string().trim().min(1),
  phones: z.array(z.string().trim().min(5)).min(1).max(5),
  note: z.string().optional(),
});

function ContactDialog({
  initial,
  onClose,
  onSaved,
}: {
  initial?: ContactRow | { name: string; phones: string[] };
  onClose: () => void;
  onSaved: () => void;
}) {
  const t = useTranslations("contacts");
  const tc = useTranslations("common");
  const isEdit = Boolean(initial && "id" in initial);
  const [name, setName] = useState(initial?.name ?? "");
  const [phones, setPhones] = useState((initial?.phones ?? [""]).join("\n"));
  const [note, setNote] = useState(
    initial && "note" in initial ? (initial.note ?? "") : "",
  );
  const [errors, setErrors] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    const parsed = contactSchema.safeParse({
      name,
      phones: phones
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean),
      note,
    });
    if (!parsed.success) {
      setErrors(
        parsed.error.issues
          .map((issue) => issue.path.join(".") || "form")
          .join(", "),
      );
      return;
    }
    setSaving(true);
    try {
      if (isEdit && initial && "id" in initial) {
        await updateContact(initial.id, parsed.data);
      } else {
        await createContact(parsed.data);
      }
      onSaved();
      onClose();
    } catch (err) {
      setErrors(err instanceof Error ? err.message : "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-4"
      role="dialog"
    >
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-5 shadow-lg">
        <h2 className="mb-3 text-base font-semibold">
          {isEdit ? t("editTitle") : t("createTitle")}
        </h2>
        <label className="mb-2 block text-sm">
          <span className="mb-1 block text-xs text-fg-muted">{t("name")}</span>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="w-full rounded-md border border-border bg-surface px-3 py-2"
            data-testid="contact-name"
          />
        </label>
        <label className="mb-2 block text-sm">
          <span className="mb-1 block text-xs text-fg-muted">
            {t("phone")} (по строке)
          </span>
          <textarea
            value={phones}
            onChange={(event) => setPhones(event.target.value)}
            rows={3}
            className="tnum w-full rounded-md border border-border bg-surface px-3 py-2"
            data-testid="contact-phones"
          />
        </label>
        <label className="mb-2 block text-sm">
          <span className="mb-1 block text-xs text-fg-muted">
            {t("position")}
          </span>
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            className="w-full rounded-md border border-border bg-surface px-3 py-2"
          />
        </label>
        {errors && (
          <p role="alert" className="mb-2 text-xs text-danger">
            {errors}
          </p>
        )}
        <div className="mt-3 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-border px-3 py-1.5 text-sm"
          >
            {tc("cancel")}
          </button>
          <button
            type="button"
            data-testid="contact-save"
            disabled={saving}
            onClick={save}
            className="rounded-md bg-accent px-4 py-1.5 text-sm font-semibold text-accent-fg disabled:opacity-50"
          >
            {tc("save")}
          </button>
        </div>
      </div>
    </div>
  );
}

function ContactsInner() {
  const t = useTranslations("contacts");
  const tc = useTranslations("common");
  const tNav = useTranslations("nav");
  const queryClient = useQueryClient();
  const params = useSearchParams();
  const fromCallId = params.get("fromCall");

  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [dialog, setDialog] = useState<
    | null
    | { mode: "create"; prefill?: { name: string; phones: string[] } }
    | {
        mode: "edit";
        contact: ContactRow;
      }
  >(null);

  const { data, isPending } = useQuery({
    queryKey: ["contacts", search, page],
    queryFn: () => fetchContacts(search, page),
  });

  // From-call flow: fetch the call, then either quick-create via the
  // dedicated endpoint or open the prefilled dialog.
  const [fromCallDone, setFromCallDone] = useState(false);
  useEffect(() => {
    if (!fromCallId || fromCallDone) return;
    setFromCallDone(true);
    (async () => {
      try {
        const detail = await fetchCallDetail(Number(fromCallId));
        const result = await contactFromCall(Number(fromCallId));
        useToastStore.getState().push({
          kind: "success",
          text: `${t("createFromCall")}: ${detail.call.counterparty_number} (+${result.linked_calls})`,
        });
        queryClient.invalidateQueries({ queryKey: ["contacts"] });
      } catch (err) {
        useToastStore.getState().push({
          kind: "error",
          text: err instanceof Error ? err.message : "error",
        });
      }
    })();
  }, [fromCallId, fromCallDone, queryClient, t]);

  const remove = useMutation({
    mutationFn: deleteContact,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["contacts"] }),
  });

  const columns: Column<ContactRow>[] = [
    {
      key: "name",
      header: t("name"),
      cell: (row) => (
        <Link
          href={`/cabinet/contacts/${row.id}`}
          className="font-medium text-accent hover:underline"
        >
          {row.name}
        </Link>
      ),
    },
    { key: "position", header: t("position"), cell: (row) => row.note || "—" },
    {
      key: "phone",
      header: t("phone"),
      cell: (row) => (
        <span className="tnum">
          {row.phones.map((phone) => formatPhone(phone)).join(", ")}
        </span>
      ),
    },
    {
      key: "responsible",
      header: t("responsible"),
      cell: (row) => (row.responsible_id ? `#${row.responsible_id}` : "—"),
    },
    {
      key: "actions",
      header: "",
      cell: (row) => (
        <span className="flex gap-2">
          <button
            type="button"
            aria-label="edit"
            onClick={() => setDialog({ mode: "edit", contact: row })}
            className="text-fg-faint hover:text-accent"
          >
            <Pencil className="size-4" />
          </button>
          <button
            type="button"
            aria-label="delete"
            onClick={async () => {
              if (
                await confirmDialog(`${tc("delete")}: ${row.name}?`, {
                  danger: true,
                })
              )
                remove.mutate(row.id);
            }}
            className="text-fg-faint hover:text-danger"
          >
            <Trash2 className="size-4" />
          </button>
        </span>
      ),
    },
  ];

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">{tNav("contacts")}</h1>
        <button
          type="button"
          data-testid="new-contact"
          onClick={() => setDialog({ mode: "create" })}
          className="rounded-md bg-accent px-3 py-2 text-sm font-semibold text-accent-fg hover:opacity-90"
        >
          {t("new")}
        </button>
      </div>

      <FilterBar
        search={search}
        onSearch={(value) => {
          setSearch(value);
          setPage(1);
        }}
      />

      <DataTable<ContactRow>
        columns={columns}
        rows={data?.results ?? []}
        loading={isPending}
        storageKey="contacts"
        empty={
          <div className="text-center">
            <Contact2 className="mx-auto size-8 text-fg-faint" />
            <p className="mt-2 text-sm font-medium">{t("emptyTitle")}</p>
            <p className="text-xs text-fg-faint">{t("emptyHint")}</p>
          </div>
        }
      />

      {dialog && (
        <ContactDialog
          initial={dialog.mode === "edit" ? dialog.contact : dialog.prefill}
          onClose={() => setDialog(null)}
          onSaved={() =>
            queryClient.invalidateQueries({ queryKey: ["contacts"] })
          }
        />
      )}
    </div>
  );
}

export default function ContactsPage() {
  return (
    <Suspense>
      <ContactsInner />
    </Suspense>
  );
}
