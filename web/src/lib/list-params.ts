/** URL search-param helpers for list pages (shareable, server-rendered filters). */

export type SearchParamsRecord = Record<string, string | string[] | undefined>;

export function firstParam(
  value: string | string[] | undefined,
  fallback = "",
): string {
  if (Array.isArray(value)) return (value[0] ?? fallback).trim();
  return (value ?? fallback).trim();
}

/** Require at least 2 chars for free-text search to avoid expensive ILIKE scans. */
export function normalizeQuery(raw: string | string[] | undefined): string {
  const q = firstParam(raw);
  return q.length >= 2 ? q : "";
}

export function triState(raw: string | string[] | undefined): "" | "1" | "0" {
  const v = firstParam(raw);
  if (v === "1" || v === "0") return v;
  return "";
}

export function buildListHref(
  basePath: string,
  params: Record<string, string | undefined | null>,
): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== "") sp.set(k, v);
  }
  const qs = sp.toString();
  return qs ? `${basePath}?${qs}` : basePath;
}

/** Drop `page` and one key when building “remove this facet” links. */
export function omitParam(
  params: Record<string, string | undefined>,
  key: string,
): Record<string, string | undefined> {
  const next = { ...params };
  delete next[key];
  delete next.page;
  return next;
}

export function hasActiveFilters(
  params: Record<string, string | undefined>,
  ignore: string[] = ["page"],
): boolean {
  return Object.entries(params).some(
    ([k, v]) => !ignore.includes(k) && v != null && v !== "",
  );
}

export type ActiveChip = {
  key: string;
  label: string;
  clearHref: string;
};
