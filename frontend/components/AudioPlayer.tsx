"use client";

/** Inline call-recording player: play button → mini player with seek,
 * 1×/1.5×/2× and download. Runs against a mock stream until real presigned
 * URLs are wired in Phase 7 (pass `mock` to simulate loading). */

import { Download, Pause, Play } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useReducer, useRef } from "react";

import {
  initialPlayerState,
  playerReducer,
  type Rate,
} from "@/lib/audio-machine";
import { formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";

const RATES: Rate[] = [1, 1.5, 2];

export function AudioPlayer({
  src,
  mock = false,
  mockDuration = 47,
}: {
  src: string;
  mock?: boolean;
  mockDuration?: number;
}) {
  const t = useTranslations("player");
  const [state, dispatch] = useReducer(playerReducer, initialPlayerState);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const mockTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // Mock playback loop (Phase 6: no real stream yet).
  useEffect(() => {
    if (state.status === "playing" && mock) {
      mockTimer.current = setInterval(() => {
        dispatch({
          type: "TICK",
          position: state.position + 0.5 * state.rate,
        });
        if (state.position >= state.duration) dispatch({ type: "ENDED" });
      }, 500);
      return () => {
        if (mockTimer.current) clearInterval(mockTimer.current);
      };
    }
    return undefined;
  }, [state, mock]);

  const start = () => {
    dispatch({ type: "LOAD" });
    if (mock) {
      setTimeout(
        () => dispatch({ type: "LOADED", duration: mockDuration }),
        300,
      );
      return;
    }
    const audio = new Audio(src);
    audioRef.current = audio;
    audio.addEventListener("loadedmetadata", () =>
      dispatch({ type: "LOADED", duration: audio.duration }),
    );
    audio.addEventListener("timeupdate", () =>
      dispatch({ type: "TICK", position: audio.currentTime }),
    );
    audio.addEventListener("ended", () => dispatch({ type: "ENDED" }));
    audio.addEventListener("error", () =>
      dispatch({ type: "ERROR", message: t("error") }),
    );
    audio.play().catch(() => dispatch({ type: "ERROR", message: t("error") }));
  };

  const toggle = () => {
    if (state.status === "playing") {
      audioRef.current?.pause();
      dispatch({ type: "PAUSE" });
    } else if (state.status === "paused") {
      audioRef.current?.play();
      dispatch({ type: "PLAY" });
    }
  };

  const seek = (position: number) => {
    if (audioRef.current) audioRef.current.currentTime = position;
    dispatch({ type: "SEEK", position });
  };

  const setRate = (rate: Rate) => {
    if (audioRef.current) audioRef.current.playbackRate = rate;
    dispatch({ type: "SET_RATE", rate });
  };

  if (state.status === "idle" || state.status === "loading") {
    return (
      <button
        type="button"
        data-testid="player-start"
        onClick={start}
        disabled={state.status === "loading"}
        aria-label={t("play")}
        className="grid size-8 place-items-center rounded-full bg-accent-soft text-accent hover:bg-accent hover:text-accent-fg disabled:animate-pulse"
      >
        <Play className="size-4" />
      </button>
    );
  }

  if (state.status === "error") {
    return (
      <span role="alert" className="text-xs text-danger">
        {state.message}
      </span>
    );
  }

  const { position, duration, rate } = state;
  return (
    <div
      data-testid="mini-player"
      className="flex w-full max-w-md items-center gap-2 rounded-full border border-border bg-surface px-2 py-1.5"
    >
      <button
        type="button"
        data-testid="player-toggle"
        onClick={toggle}
        className="grid size-7 shrink-0 place-items-center rounded-full bg-accent text-accent-fg"
      >
        {state.status === "playing" ? (
          <Pause className="size-3.5" />
        ) : (
          <Play className="size-3.5" />
        )}
      </button>

      <span className="tnum shrink-0 text-xs text-fg-muted">
        {formatDuration(position)}
      </span>
      <input
        type="range"
        data-testid="player-seek"
        min={0}
        max={duration}
        step={1}
        value={position}
        onChange={(event) => seek(Number(event.target.value))}
        className="h-1 min-w-0 flex-1 accent-[var(--accent)]"
      />
      <span className="tnum shrink-0 text-xs text-fg-faint">
        {formatDuration(duration)}
      </span>

      <div className="flex shrink-0 gap-0.5">
        {RATES.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setRate(option)}
            className={cn(
              "tnum rounded px-1.5 py-0.5 text-[10px] font-semibold",
              option === rate
                ? "bg-accent text-accent-fg"
                : "text-fg-faint hover:text-fg",
            )}
          >
            {option}×
          </button>
        ))}
      </div>

      <a
        href={src}
        download
        aria-label={t("download")}
        className="grid size-7 shrink-0 place-items-center rounded-full text-fg-muted hover:bg-surface-2"
      >
        <Download className="size-3.5" />
      </a>
    </div>
  );
}
