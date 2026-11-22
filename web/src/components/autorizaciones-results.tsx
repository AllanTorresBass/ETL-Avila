import Link from "next/link";
import { AuthorizationLineCard } from "@/components/authorization-line-card";
import { AuthorizationStatusPill } from "@/components/authorization-status-pill";
import { EmptyState } from "@/components/empty-state";
import { DEFAULT_PAGE_SIZE, Pagination, parsePage } from "@/components/pagination";
import { ResultCount } from "@/components/result-count";
import { queryAuthorizationList } from "@/lib/authorization-data";
import {
  authorizationListFilters,
  autorizacionFilterParams,
  type AutorizacionesSearchInput,
} from "@/lib/authorization-filters";
import { formatInvoiceNumber } from "@/lib/format";
import { firstParam, hasActiveFilters } from "@/lib/list-params";

/** Filtered authorization lines + pagination (streamed under Suspense). */
export async function AutorizacionesResults({ sp }: { sp: AutorizacionesSearchInput }) {
  const params = autorizacionFilterParams(sp);
  const result = await queryAuthorizationList(
    authorizationListFilters(params, DEFAULT_PAGE_SIZE, parsePage(firstParam(sp.page) || undefined)),
  ).catch(() => null);

  if (!result) {
    return (
      <div id="lista" className="scroll-mt-24">
        <EmptyState
          title="No se pudieron cargar las autorizaciones"
          hint="Revisa la conexión a Neon y vuelve a cargar la página."
        />
      </div>
    );
  }

  const { total, page, rows } = result;
  const filtersActive = hasActiveFilters(params);

  return (
    <div id="lista" className="scroll-mt-24 space-y-3">
      <div role="status">
        <ResultCount shown={rows.length} total={total} page={page} pageSize={DEFAULT_PAGE_SIZE} />
      </div>
      {rows.length === 0 ? (
        <EmptyState
          title={filtersActive ? "No se encontraron autorizaciones" : "Aún no hay autorizaciones"}
          hint={
            filtersActive
              ? "Cambia la búsqueda o quita algún filtro."
              : "Ejecuta load_authorization_lines y match_auth_lines --apply para cargarlas desde los libros."
          }
        />
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {rows.map((row) => (
            <li key={row.id}>
              <AuthorizationLineCard
                line={row}
                href={`/autorizaciones/${row.id}`}
                badge={<AuthorizationStatusPill status={row.match_status} invoiceId={row.invoice_id} />}
                extra={
                  <>
                    {row.account_name ? <span>{row.account_name}</span> : null}
                    {row.especialidad ? <span>{row.especialidad}</span> : null}
                    {row.person_id ? (
                      <Link href={`/personas/${row.person_id}`} className="text-brand hover:underline">
                        {row.person_name || "Paciente"}
                      </Link>
                    ) : null}
                    {row.titular_id && row.titular_id !== row.person_id ? (
                      <Link href={`/personas/${row.titular_id}`} className="text-brand hover:underline">
                        Titular: {row.titular_name || "—"}
                      </Link>
                    ) : null}
                    {row.invoice_id ? (
                      <Link href={`/facturas/${row.invoice_id}`} className="text-brand hover:underline">
                        {formatInvoiceNumber(row.invoice_number)}
                      </Link>
                    ) : null}
                  </>
                }
              />
            </li>
          ))}
        </ul>
      )}
      <Pagination
        page={page}
        pageSize={DEFAULT_PAGE_SIZE}
        total={total}
        shown={rows.length}
        basePath="/autorizaciones"
        searchParams={params}
        hash="lista"
      />
    </div>
  );
}
