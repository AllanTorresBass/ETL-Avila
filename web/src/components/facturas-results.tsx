import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { ListExportBar } from "@/components/list-export-bar";
import {
  Pagination,
  DEFAULT_PAGE_SIZE,
  parsePage,
} from "@/components/pagination";
import { ResultCount } from "@/components/result-count";
import type { CsvTable } from "@/lib/csv";
import { formatAccount, formatInvoiceNumber } from "@/lib/format";
import { queryFacturaList, type FacturaListRow } from "@/lib/factura-list-data";
import {
  firstParam,
  hasActiveFilters,
  normalizeQuery,
  triState,
} from "@/lib/list-params";

/** Max rows for CSV + print table (all filtered matches, not just the current page). */
export const FACTURAS_EXPORT_LIMIT = 5000;

export type FacturasSearchInput = {
  q?: string;
  account?: string;
  year?: string;
  month?: string;
  has_person?: string;
  has_titular?: string;
  has_docs?: string;
  page?: string;
};

function yesNo(value: boolean): string {
  return value ? "sí" : "no";
}

function buildFacturasCsv(rows: FacturaListRow[]): CsvTable[] {
  return [
    {
      name: "facturas",
      headers: [
        "id",
        "factura",
        "cuenta",
        "year",
        "month",
        "lote",
        "docs",
        "tiene_persona",
        "tiene_titular",
      ],
      rows: rows.map((inv) => [
        inv.id,
        inv.invoice_number || "",
        inv.account || "",
        inv.year || "",
        inv.month || "",
        inv.lote || "",
        inv.docs,
        yesNo(inv.has_person > 0),
        yesNo(inv.has_titular > 0),
      ]),
    },
  ];
}

/** Filtered facturas list + pagination + export (streamed under Suspense). */
export async function FacturasResults({ sp }: { sp: FacturasSearchInput }) {
  const query = normalizeQuery(sp.q);
  const account = firstParam(sp.account);
  const year = firstParam(sp.year);
  const month = firstParam(sp.month);
  const hasPerson = triState(sp.has_person);
  const hasTitular = triState(sp.has_titular);
  const hasDocs = triState(sp.has_docs);
  const requestedPage = parsePage(firstParam(sp.page) || undefined);
  const like = `%${query}%`;

  const filtersActive = hasActiveFilters({
    q: query || undefined,
    account: account || undefined,
    year: year || undefined,
    month: month || undefined,
    has_person: hasPerson || undefined,
    has_titular: hasTitular || undefined,
    has_docs: hasDocs || undefined,
  });

  const { total, page, pageRows: invoices, exportRows: exportInvoices } = await queryFacturaList({
    query,
    like,
    account,
    year,
    month,
    hasPerson,
    hasTitular,
    hasDocs,
    pageSize: DEFAULT_PAGE_SIZE,
    requestedPage,
    exportLimit: FACTURAS_EXPORT_LIMIT,
  });

  const filterParams: Record<string, string | undefined> = {
    q: query || undefined,
    account: account || undefined,
    year: year || undefined,
    month: month || undefined,
    has_person: hasPerson || undefined,
    has_titular: hasTitular || undefined,
    has_docs: hasDocs || undefined,
  };

  const csvTables = buildFacturasCsv(exportInvoices);
  const exportCapped = total > FACTURAS_EXPORT_LIMIT;
  const exportNote = exportCapped
    ? `Exportando las primeras ${FACTURAS_EXPORT_LIMIT.toLocaleString("es-VE")} de ${total.toLocaleString("es-VE")}`
    : undefined;

  return (
    <div id="lista" className="scroll-mt-24 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <ResultCount
          shown={invoices.length}
          total={total}
          page={page}
          pageSize={DEFAULT_PAGE_SIZE}
        />
        <ListExportBar
          filenamePrefix="avila-facturas"
          tables={csvTables}
          disabled={exportInvoices.length === 0}
          note={exportNote}
        />
      </div>

      {invoices.length === 0 ? (
        <EmptyState
          title={filtersActive ? "No hay coincidencias" : "Aún no hay facturas"}
          hint={
            filtersActive
              ? "Prueba quitar filtros o ampliar la búsqueda (mínimo 2 caracteres)."
              : "Ejecuta la carga de documentos para poblar el archivo."
          }
        />
      ) : (
        <ul className="facturas-screen-list divide-y divide-border overflow-hidden rounded-3xl border border-border bg-card shadow-sm print:hidden">
          {invoices.map((inv) => (
            <li key={inv.id}>
              <Link
                href={`/facturas/${inv.id}`}
                className="flex flex-wrap items-center justify-between gap-3 px-4 py-3.5 transition-colors hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring sm:px-5"
              >
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-foreground">
                      {formatInvoiceNumber(inv.invoice_number)}
                    </span>
                    {inv.has_titular === 0 ? (
                      <span className="rounded-full bg-warning-soft px-2 py-0.5 text-[11px] font-medium text-warning">
                        Sin titular
                      </span>
                    ) : null}
                    {inv.has_person === 0 ? (
                      <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                        Sin persona
                      </span>
                    ) : null}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {[
                      formatAccount(inv.account),
                      [inv.month, inv.year].filter(Boolean).join(" ") || null,
                      inv.lote ? `lote ${inv.lote}` : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                </div>
                <div className="shrink-0 text-xs tabular-nums text-muted-foreground">
                  {inv.docs} pág{inv.docs === 1 ? "" : "s"}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {exportInvoices.length > 0 ? (
        <div className="facturas-print-table hidden print:block">
          <h2 className="mb-3 text-base font-semibold text-foreground">Facturas</h2>
          {exportCapped ? (
            <p className="mb-2 text-xs text-muted-foreground">
              Mostrando las primeras {FACTURAS_EXPORT_LIMIT.toLocaleString("es-VE")} de{" "}
              {total.toLocaleString("es-VE")} coincidencias.
            </p>
          ) : null}
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-border">
                <th className="py-1.5 pr-2 font-medium">Factura</th>
                <th className="py-1.5 pr-2 font-medium">Cuenta</th>
                <th className="py-1.5 pr-2 font-medium">Periodo</th>
                <th className="py-1.5 pr-2 font-medium">Lote</th>
                <th className="py-1.5 pr-2 font-medium">Docs</th>
                <th className="py-1.5 pr-2 font-medium">Persona</th>
                <th className="py-1.5 font-medium">Titular</th>
              </tr>
            </thead>
            <tbody>
              {exportInvoices.map((inv) => (
                <tr key={inv.id} className="border-b border-border/70">
                  <td className="py-1.5 pr-2">{formatInvoiceNumber(inv.invoice_number)}</td>
                  <td className="py-1.5 pr-2">{formatAccount(inv.account) || "—"}</td>
                  <td className="py-1.5 pr-2 tabular-nums">
                    {[inv.month, inv.year].filter(Boolean).join("/") || "—"}
                  </td>
                  <td className="py-1.5 pr-2 tabular-nums">{inv.lote || "—"}</td>
                  <td className="py-1.5 pr-2 tabular-nums">{inv.docs}</td>
                  <td className="py-1.5 pr-2">{yesNo(inv.has_person > 0)}</td>
                  <td className="py-1.5">{yesNo(inv.has_titular > 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="facturas-pagination print:hidden">
        <Pagination
          page={page}
          pageSize={DEFAULT_PAGE_SIZE}
          total={total}
          shown={invoices.length}
          basePath="/facturas"
          searchParams={filterParams}
          hash="lista"
        />
      </div>
    </div>
  );
}
