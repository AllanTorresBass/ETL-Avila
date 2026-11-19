const usd = new Intl.NumberFormat("es-VE", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const usdCompact = new Intl.NumberFormat("es-VE", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});

const compact = new Intl.NumberFormat("es-VE", {
  notation: "compact",
  maximumFractionDigits: 1,
});

const monthShort = new Intl.DateTimeFormat("es-VE", { month: "short", year: "2-digit", timeZone: "UTC" });
const dateTime = new Intl.DateTimeFormat("es-VE", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "America/Caracas",
});

export function formatUsd(value: number): string {
  return usd.format(value);
}

export function formatUsdCompact(value: number): string {
  return usdCompact.format(value);
}

export function formatCompact(value: number): string {
  return compact.format(value);
}

export function formatPercent(ratio: number): string {
  return `${Math.round(ratio * 100)}%`;
}

/** "2025-03" -> "mar 25" */
export function formatMonthKey(key: string): string {
  const [year, month] = key.split("-").map(Number);
  return monthShort.format(new Date(Date.UTC(year, month - 1, 1)));
}

export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const date = typeof value === "string" ? new Date(value) : value;
  return Number.isNaN(date.getTime()) ? "—" : dateTime.format(date);
}

export function formatDuration(start: string | Date, end: string | Date | null): string {
  if (!end) return "En curso";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "—";
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ${seconds % 60} s`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

/** Relative change vs a previous period; null when there is nothing to compare. */
export function percentChange(current: number, previous: number): number | null {
  if (!Number.isFinite(previous) || previous <= 0) return null;
  return (current - previous) / previous;
}
