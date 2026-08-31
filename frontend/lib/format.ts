/** Formatting helpers — durations and phone numbers (contract §1 shapes). */

/** 47 → "0:47", 3599 → "59:59", 3661 → "1:01:01". Always tabular-safe. */
export function formatDuration(totalSeconds: number): string {
  if (!Number.isFinite(totalSeconds) || totalSeconds < 0) return "0:00";
  const s = Math.floor(totalSeconds);
  const hours = Math.floor(s / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  const seconds = s % 60;
  const mm = hours > 0 ? String(minutes).padStart(2, "0") : String(minutes);
  const ss = String(seconds).padStart(2, "0");
  return hours > 0 ? `${hours}:${mm}:${ss}` : `${mm}:${ss}`;
}

/** "+998901234567" → "+998 90 123-45-67"; foreign/short numbers pass through. */
export function formatPhone(raw: string | null | undefined): string {
  if (!raw) return "—";
  const m = /^\+998(\d{2})(\d{3})(\d{2})(\d{2})$/.exec(raw);
  if (!m) return raw;
  return `+998 ${m[1]} ${m[2]}-${m[3]}-${m[4]}`;
}

/** 300000 → "300 000" (narrow no-break space groups). */
export function formatUzs(amount: number): string {
  return new Intl.NumberFormat("ru-RU").format(amount).replace(/ /g, " ");
}

/** "how long ago" humanizer for the unanswered report (ru units). */
export function humanizeAgo(iso: string, now = new Date()): string {
  const diffMs = now.getTime() - new Date(iso).getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 60) return `${Math.max(minutes, 0)} мин`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ч`;
  const days = Math.floor(hours / 24);
  return `${days} дн`;
}
