import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { DEFAULT_PAGE_SIZE, Pagination, parsePage } from "@/components/pagination";
import { ResultCount } from "@/components/result-count";
import { firstParam, hasActiveFilters, normalizeQuery, triState } from "@/lib/list-params";
import { queryMedicoList, type MedicoListRow } from "@/lib/medico-data";

export type MedicosSearchInput = {
  q?: string;
  area?: string;
  especialidad?: string;
  has_mpps?: string;
  page?: string;
};

export function medicoFilterParams(sp: MedicosSearchInput): Record<string, string | undefined> {
  return {
    q: normalizeQuery(sp.q) || undefined,
    area: firstParam(sp.area) || undefined,
    especialidad: firstParam(sp.especialidad) || undefined,
    has_mpps: triState(sp.has_mpps) || undefined,
  };
}

function doctorTitle(row: MedicoListRow): string {
  return `${row.title === "dra" ? "Dra." : "Dr."} ${row.full_name}`;
}

/** Filtered médicos directory + pagination (streamed under Suspense). */
export async function MedicosResults({ sp }: { sp: MedicosSearchInput }) {
  const params = medicoFilterParams(sp);
  const query = params.q || "";
  const { total, page, rows } = await queryMedicoList({
    query,
    like: `%${query}%`,
    area: params.area || "",
    especialidad: params.especialidad || "",
    hasMpps: triState(sp.has_mpps),
    pageSize: DEFAULT_PAGE_SIZE,
    requestedPage: parsePage(firstParam(sp.page) || undefined),
  });
  const filtersActive = hasActiveFilters(params);

  return (
    <div id="lista" className="scroll-mt-24 space-y-3">
      <div role="status">
        <ResultCount shown={rows.length} total={total} page={page} pageSize={DEFAULT_PAGE_SIZE} />
      </div>
      {rows.length === 0 ? (
        <EmptyState
          title={filtersActive ? "No se encontraron médicos" : "Aún no hay médicos"}
          hint={
            filtersActive
              ? "Intenta cambiar los términos de búsqueda o el filtro de especialidad."
              : "Ejecuta clinical_extract, medico_resolve y clinical_apply --apply para poblar el directorio."
          }
        />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {rows.map((row) => (
            <li key={row.id}>
              <Link
                href={`/medicos/${row.id}`}
                className="flex h-full flex-col justify-between gap-3 rounded-3xl border border-border bg-card p-5 shadow-sm transition hover:border-brand/40 hover:shadow-md focus-visible:outline-2 focus-visible:outline-ring"
              >
                <div className="space-y-1.5">
                  <p className="font-medium text-foreground">{doctorTitle(row)}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {row.especialidad ? (
                      <span className="rounded-full bg-brand/10 px-2.5 py-0.5 text-[11px] font-medium text-brand">
                        {row.especialidad}
                      </span>
                    ) : (
                      <span className="rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                        Sin especialidad
                      </span>
                    )}
                    {row.area_name ? (
                      <span className="rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                        {row.area_name}
                      </span>
                    ) : null}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {row.mpps ? `MPPS ${row.mpps}` : "Sin MPPS leído"}
                    {row.degree ? ` · ${row.degree}` : ""}
                  </p>
                </div>
                <p className="text-xs tabular-nums text-muted-foreground">
                  {row.atenciones.toLocaleString("es-VE")} atenciones · {row.pacientes.toLocaleString("es-VE")} pacientes
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <Pagination
        page={page}
        pageSize={DEFAULT_PAGE_SIZE}
        total={total}
        shown={rows.length}
        basePath="/medicos"
        searchParams={params}
        hash="lista"
      />
    </div>
  );
}
