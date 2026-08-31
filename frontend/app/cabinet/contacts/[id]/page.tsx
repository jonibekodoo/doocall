"use client";

/** §6.3 Contact card — details + call history with playback. */

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";

import { DirectionIcon } from "@/components/calls-shared";
import { CallAudioButton } from "@/components/CallAudioButton";
import { fetchContactDetail } from "@/lib/api/endpoints";
import { formatDuration, formatPhone } from "@/lib/format";

export default function ContactCardPage() {
  const t = useTranslations("contacts");
  const params = useParams<{ id: string }>();
  const contactId = Number(params.id);

  const { data, isPending } = useQuery({
    queryKey: ["contact", contactId],
    queryFn: () => fetchContactDetail(contactId),
    enabled: Number.isFinite(contactId),
  });

  if (isPending) {
    return <div className="h-64 animate-pulse rounded-lg bg-surface-2" />;
  }
  if (!data) return null;

  const { contact, calls } = data;
  return (
    <div>
      <Link
        href="/cabinet/contacts"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-accent"
      >
        <ArrowLeft className="size-4" /> {t("name")}
      </Link>

      <div className="rounded-lg border border-border bg-surface p-5">
        <h1 className="text-xl font-semibold" data-testid="contact-card-name">
          {contact.name}
        </h1>
        {contact.note && (
          <p className="mt-1 text-sm text-fg-muted">{contact.note}</p>
        )}
        <p className="tnum mt-2 text-sm">
          {contact.phones.map((phone) => formatPhone(phone)).join(" · ")}
        </p>
      </div>

      <h2 className="mb-2 mt-6 text-sm font-semibold text-fg-muted">
        {t("history")}
      </h2>
      <ul className="divide-y divide-border rounded-lg border border-border bg-surface">
        {calls.length === 0 && (
          <li className="px-4 py-6 text-center text-sm text-fg-faint">—</li>
        )}
        {calls.map((call) => (
          <li
            key={call.id}
            className="flex items-center gap-2.5 px-4 py-2 text-sm"
          >
            <DirectionIcon direction={call.direction} />
            <span className="tnum min-w-0 flex-1 truncate text-xs text-fg-muted">
              {new Date(call.start_time).toLocaleString("ru-RU")}
            </span>
            <span className="tnum text-xs">
              {formatDuration(call.duration)}
            </span>
            {call.status === "answered" && <CallAudioButton callId={call.id} />}
          </li>
        ))}
      </ul>
    </div>
  );
}
