"use client";

/** Inline audio for a call row: on first click, fetches the call detail to
 * obtain the REAL presigned URL, then mounts the AudioPlayer against it.
 * Falls back to nothing when the call has no stored audio. */

import { Play } from "lucide-react";
import { useState } from "react";

import { AudioPlayer } from "@/components/AudioPlayer";
import { fetchCallDetail } from "@/lib/api/endpoints";

export function CallAudioButton({ callId }: { callId: number }) {
  const [url, setUrl] = useState<string | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "none" | "ready">(
    "idle",
  );

  const load = async () => {
    setState("loading");
    try {
      const detail = await fetchCallDetail(callId);
      const primary = detail.call.audios.find(
        (audio) => audio.kind === "primary",
      );
      if (primary) {
        setUrl(primary.url);
        setState("ready");
      } else {
        setState("none");
      }
    } catch {
      setState("none");
    }
  };

  if (state === "ready" && url) return <AudioPlayer src={url} />;
  if (state === "none") return null;

  return (
    <button
      type="button"
      data-testid="row-audio"
      onClick={load}
      disabled={state === "loading"}
      aria-label="play"
      className="grid size-7 shrink-0 place-items-center rounded-full bg-accent-soft text-accent hover:bg-accent hover:text-accent-fg disabled:animate-pulse"
    >
      <Play className="size-3.5" />
    </button>
  );
}
