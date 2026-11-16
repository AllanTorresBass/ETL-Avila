import Link from "next/link";
import { Input } from "@/components/ui/input";
import type { ActiveChip } from "@/lib/list-params";

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

export function ListFilterBar({
  searchName = "q",
  searchValue = "",
  searchPlaceholder = "Buscar…",
  searchLabel = "Buscar",
  selects = [],
  chipGroups = [],
  activeChips = [],
  clearHref,
  submitLabel = "Filtrar",
}: {
  searchName?: string;
  searchValue?: string;
  searchPlaceholder?: string;
  searchLabel?: string;
  selects?: FilterSelect[];
  chipGroups?: FilterChipGroup[];
  activeChips?: ActiveChip[];
  clearHref?: string;
  submitLabel?: string;
}) {
  return (
    <div className="space-y-3">
      <form className="flex flex-wrap items-end gap-3" method="get">
        <label className="block min-w-[12rem] flex-1 text-xs font-medium text-slate-600">
          {searchLabel}
          <Input
            name={searchName}
            defaultValue={searchValue}
            placeholder={searchPlaceholder}
            className="mt-1 rounded-xl border-slate-200"
            aria-label={searchLabel}
          />
        </label>
        {selects.map((sel) => (
          <label key={sel.name} className="block text-xs font-medium text-slate-600">
            {sel.label}
            <select
              name={sel.name}
              defaultValue={sel.value}
              className="mt-1 block min-w-[10rem] rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs"
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
        {/* Preserve chip params (type, status, …) when the GET form submits */}
        {chipGroups.map((g) =>
          g.value ? (
            <input key={`hidden-${g.param}`} type="hidden" name={g.param} value={g.value} />
          ) : null,
        )}
        <button
          type="submit"
          className="btn-green-gradient rounded-full px-5 py-2.5 text-xs font-medium text-white focus-visible:ring-2 focus-visible:ring-[#0F7A33] focus-visible:ring-offset-2"
        >
          {submitLabel}
        </button>
        {clearHref ? (
          <Link
            href={clearHref}
            className="rounded-full border border-slate-200 bg-white px-4 py-2.5 text-xs font-medium text-slate-600"
          >
            Limpiar
          </Link>
        ) : null}
      </form>

      {chipGroups.map((group) => (
        <div key={group.param} className="space-y-1.5">
          <p className="text-xs font-medium tracking-wider text-slate-400 uppercase">
            {group.label}
          </p>
          <div className="flex flex-wrap gap-2" role="group" aria-label={group.label}>
            <Link
              href={group.allHref}
              aria-pressed={!group.value}
              className={`rounded-full px-3 py-1.5 text-xs font-medium ${
                !group.value
                  ? "bg-[#033CA0] text-white"
                  : "border border-slate-200 bg-white text-slate-600"
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
                    ? "bg-[#033CA0] text-white"
                    : "border border-slate-200 bg-white text-slate-600"
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
              className="inline-flex items-center gap-1.5 rounded-full bg-[#0A2A6B]/8 px-3 py-1 text-xs font-medium text-[#0A2A6B]"
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
