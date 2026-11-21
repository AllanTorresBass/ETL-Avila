"use client";

import Link from "next/link";
import { useEffect, useRef, useState, useTransition, type FormEvent } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Input } from "@/components/ui/input";
import { buildListHref, type ActiveChip } from "@/lib/list-params";

function effectiveQuery(raw: string, minLength: number): string {
  const q = raw.trim();
  return q.length >= minLength ? q : "";
}

export type FilterSelect = {
  name: string;
  label: string;
  value: string;
  options: { value: string; label: string }[];
  emptyLabel: string;
};

export type FilterChipGroup = {
  param: string;
  label: string;
  value: string;
  allHref: string;
  options: { value: string; label: string; href: string; count?: number }[];
};

const SEARCH_DEBOUNCE_MS = 350;

function selectsSignature(selects: FilterSelect[]): string {
  return selects.map((s) => `${s.name}=${s.value}`).join("&");
}

function draftFromSelects(selects: FilterSelect[]): Record<string, string> {
  return Object.fromEntries(selects.map((s) => [s.name, s.value]));
}

/** Live server filters: debounced search + immediate select changes update the URL. */
export function ListFilterBar({
  searchName = "q",
  searchValue = "",
  searchPlaceholder = "Buscar…",
  searchLabel = "Buscar",
  selects = [],
  chipGroups = [],
  activeChips = [],
  clearHref,
  hash,
  carry = {},
  minQueryLength = 2,
}: {
  searchName?: string;
  searchValue?: string;
  searchPlaceholder?: string;
  searchLabel?: string;
  selects?: FilterSelect[];
  chipGroups?: FilterChipGroup[];
  activeChips?: ActiveChip[];
  clearHref?: string;
  /** Optional URL hash (e.g. `lista`) appended on filter navigation. */
  hash?: string;
  /** Params that stay in the URL when the search changes. */
  carry?: Record<string, string>;
  minQueryLength?: number;
  /** @deprecated Live filters no longer use a submit button. */
  submitLabel?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [, startTransition] = useTransition();
  const [draftQ, setDraftQ] = useState(searchValue);
  const [draftSelects, setDraftSelects] = useState(() => draftFromSelects(selects));
  const selectSig = selectsSignature(selects);
  const prevSearchValue = useRef(searchValue);
  const prevSelectSig = useRef(selectSig);

  useEffect(() => {
    const selectsChanged = prevSelectSig.current !== selectSig;
    prevSelectSig.current = selectSig;
    setDraftSelects(draftFromSelects(selects));

    if (selectsChanged) {
      prevSearchValue.current = searchValue;
      setDraftQ(searchValue);
      return;
    }

    const prev = prevSearchValue.current;
    prevSearchValue.current = searchValue;
    setDraftQ((current) => {
      const currentNorm = effectiveQuery(current, minQueryLength);
      const prevNorm = effectiveQuery(prev, minQueryLength);
      const nextNorm = effectiveQuery(searchValue, minQueryLength);
      // Keep keystrokes that are ahead of the in-flight URL update.
      if (currentNorm !== prevNorm && currentNorm !== nextNorm) return current;
      return searchValue;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- sync from URL props
  }, [searchValue, selectSig, minQueryLength]);

  function pushFilters(patch: Record<string, string | undefined>) {
    const qRaw = (patch[searchName] ?? draftQ).trim();
    const params: Record<string, string | undefined> = {
      [searchName]: qRaw.length >= minQueryLength ? qRaw : undefined,
    };
    for (const sel of selects) {
      const v = patch[sel.name] ?? draftSelects[sel.name];
      params[sel.name] = v || undefined;
    }
    for (const group of chipGroups) {
      const v = patch[group.param] ?? group.value;
      if (v) params[group.param] = v;
    }
    for (const [key, value] of Object.entries(carry)) {
      if (value) params[key] = value;
    }
    const href = `${buildListHref(pathname, params)}${hash ? `#${hash}` : ""}`;
    startTransition(() => {
      router.push(href, { scroll: false });
    });
  }

  useEffect(() => {
    const handle = window.setTimeout(() => {
      const nextQ = effectiveQuery(draftQ, minQueryLength);
      const urlQ = effectiveQuery(searchValue, minQueryLength);
      if (nextQ === urlQ) return;
      pushFilters({ [searchName]: nextQ });
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
    // Intentionally depend on draftQ only — select changes navigate immediately.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- debounce search only
  }, [draftQ]);

  function onSelectChange(name: string, value: string) {
    setDraftSelects((prev) => ({ ...prev, [name]: value }));
    pushFilters({ [name]: value || undefined });
  }

  function onSearchSubmit(e: FormEvent) {
    e.preventDefault();
    pushFilters({ [searchName]: effectiveQuery(draftQ, minQueryLength) });
  }

  const shortQuery = draftQ.trim().length > 0 && draftQ.trim().length < minQueryLength;

  return (
    <div className="space-y-3">
      <form className="flex flex-wrap items-end gap-3" onSubmit={onSearchSubmit} role="search">
        <label className="block min-w-[12rem] flex-1 text-xs font-medium text-muted-foreground">
          {searchLabel}
          <Input
            name={searchName}
            value={draftQ}
            onChange={(e) => setDraftQ(e.target.value)}
            placeholder={searchPlaceholder}
            className="mt-1 rounded-xl border-border"
            aria-label={searchLabel}
            autoComplete="off"
          />
        </label>
        {selects.map((sel) => (
          <label key={sel.name} className="block text-xs font-medium text-muted-foreground">
            {sel.label}
            <select
              name={sel.name}
              value={draftSelects[sel.name] ?? ""}
              onChange={(e) => onSelectChange(sel.name, e.target.value)}
              className="mt-1 block min-w-[10rem] rounded-xl border border-border bg-card px-4 py-2.5 text-xs"
              aria-label={sel.label}
            >
              <option value="">{sel.emptyLabel}</option>
              {sel.options.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        ))}
        {clearHref ? (
          <Link
            href={clearHref}
            className="rounded-full border border-border bg-card px-4 py-2.5 text-xs font-medium text-muted-foreground"
          >
            Limpiar
          </Link>
        ) : null}
      </form>

      {shortQuery ? (
        <p role="status" className="text-sm text-muted-foreground">
          Escribe al menos {minQueryLength} caracteres para buscar.
        </p>
      ) : null}

      {chipGroups.map((group) => (
        <div key={group.param} className="space-y-1.5">
          <p className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
            {group.label}
          </p>
          <div className="flex flex-wrap gap-2" role="group" aria-label={group.label}>
            <Link
              href={group.allHref}
              aria-pressed={!group.value}
              className={`rounded-full px-3 py-1.5 text-xs font-medium ${
                !group.value
                  ? "bg-brand text-white"
                  : "border border-border bg-card text-muted-foreground"
              }`}
            >
              Todos
            </Link>
            {group.options.map((o) => (
              <Link
                key={o.value}
                href={o.href}
                aria-pressed={group.value === o.value}
                className={`rounded-full px-3 py-1.5 text-xs font-medium ${
                  group.value === o.value
                    ? "bg-brand text-white"
                    : "border border-border bg-card text-muted-foreground"
                }`}
              >
                {o.label}
                {o.count != null ? ` (${o.count})` : ""}
              </Link>
            ))}
          </div>
        </div>
      ))}

      {activeChips.length > 0 ? (
        <div className="flex flex-wrap gap-2" aria-label="Filtros activos">
          {activeChips.map((chip) => (
            <Link
              key={chip.key}
              href={chip.clearHref}
              className="inline-flex items-center gap-1.5 rounded-full bg-secondary px-3 py-1 text-xs font-medium text-foreground"
            >
              {chip.label}
              <span aria-hidden="true">×</span>
              <span className="sr-only">Quitar filtro {chip.label}</span>
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  );
}
