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
import { ROLE_LABELS } from "@/lib/db";
import {
  formatDateEs,
  formatDocumentCount,
  formatFacturaCount,
  formatIdentity,
} from "@/lib/format";
import { isIncompleteName } from "@/lib/persona-data";
import { queryPersonaList, type PersonaListRow } from "@/lib/persona-list-data";
import {
  firstParam,
  hasActiveFilters,
  normalizeQuery,
  triState,
} from "@/lib/list-params";

/** Max rows for CSV + print table (all filtered matches, not just the current page). */
export const PERSONAS_EXPORT_LIMIT = 5000;

function hasContactGaps(gap: unknown): boolean {
  if (!gap || typeof gap !== "object") return false;
  return Object.values(gap as Record<string, unknown>).some(
    (v) => typeof v === "string" && v !== "filled",
  );
}

export type PersonasSearchInput = {
  q?: string;
  has_ci?: string;
  has_phone?: string;
  has_authorization?: string;
  has_invoice?: string;
  has_contact_gap?: string;
  incomplete_name?: string;
  role?: string;
  account?: string;
  page?: string;
};

function yesNo(value: boolean): string {
  return value ? "sí" : "no";
}

function personSummary(person: PersonaListRow): string {
  const parts = [formatIdentity(person.identity_type, person.identity_number)];
  const phone = person.phone?.trim();
  if (phone) parts.push(`Tel. ${phone}`);
  if (person.birth_date) parts.push(`Nació el ${formatDateEs(person.birth_date)}`);
  return parts.join(" · ");
}

function roleCountLabel(role: string, count: number): string {
  return `${role} · ${formatFacturaCount(count)}`;
}

function buildPersonasCsv(people: PersonaListRow[]): CsvTable[] {
  return [
    {
      name: "personas",
      headers: [
        "id",
        "nombre",
        "tipo_id",
        "ci",
        "telefono",
        "fecha_nacimiento",
        "titular_n",
        "beneficiario_n",
        "docs",
        "nombre_incompleto",
        "gaps_contacto",
      ],
      rows: people.map((person) => [
        person.id,
        person.full_name || "",
        person.identity_type,
        person.identity_number || "",
        person.phone || "",
        person.birth_date ? formatDateEs(person.birth_date) : "",
        person.titular_n,
        person.beneficiario_n,
        person.docs,
        yesNo(isIncompleteName(person.full_name, person.identity_number)),
        yesNo(hasContactGaps(person.contact_gap)),
      ]),
    },
  ];
}

/** Filtered personas list + pagination (streamed under Suspense). */
export async function PersonasResults({ sp }: { sp: PersonasSearchInput }) {
  const query = normalizeQuery(sp.q);
  const hasCi = triState(sp.has_ci);
  const hasPhone = triState(sp.has_phone);
  const hasAuthorization = triState(sp.has_authorization);
  const hasInvoice = triState(sp.has_invoice);
  const hasContactGap = triState(sp.has_contact_gap);
  const incompleteName = triState(sp.incomplete_name);
  const role = firstParam(sp.role);
  const account = firstParam(sp.account);
  const requestedPage = parsePage(firstParam(sp.page) || undefined);
  const like = `%${query}%`;
  const roleOk = role === "titular" || role === "beneficiario" || role === "unknown";
  const roleFilter = roleOk ? role : "";
  const filtersActive = hasActiveFilters({
    q: query || undefined,
    has_ci: hasCi || undefined,
    has_phone: hasPhone || undefined,
    has_authorization: hasAuthorization || undefined,
    has_invoice: hasInvoice || undefined,
    has_contact_gap: hasContactGap || undefined,
    incomplete_name: incompleteName || undefined,
    role: roleFilter || undefined,
    account: account || undefined,
  });

  const { total, page, pageRows: people, exportRows: exportPeople } = await queryPersonaList({
    query,
    like,
    hasCi,
    hasPhone,
    hasAuthorization,
    hasInvoice,
    hasContactGap,
    incompleteName,
    roleFilter,
    account,
    pageSize: DEFAULT_PAGE_SIZE,
    requestedPage,
    exportLimit: PERSONAS_EXPORT_LIMIT,
  });

  const filterParams: Record<string, string | undefined> = {
    q: query || undefined,
    has_ci: hasCi || undefined,
    has_phone: hasPhone || undefined,
    has_authorization: hasAuthorization || undefined,
    has_invoice: hasInvoice || undefined,
    has_contact_gap: hasContactGap || undefined,
    incomplete_name: incompleteName || undefined,
    role: roleFilter || undefined,
    account: account || undefined,
  };

  const csvTables = buildPersonasCsv(exportPeople);
  const exportCapped = total > PERSONAS_EXPORT_LIMIT;
  const exportNote = exportCapped
    ? `Exportando las primeras ${PERSONAS_EXPORT_LIMIT.toLocaleString("es-VE")} de ${total.toLocaleString("es-VE")}`
    : undefined;

  return (
    <div id="lista" className="scroll-mt-24 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <ResultCount
          shown={people.length}
          total={total}
          page={page}
          pageSize={DEFAULT_PAGE_SIZE}
        />
        <ListExportBar
          filenamePrefix="avila-personas"
          tables={csvTables}
          disabled={exportPeople.length === 0}
          note={exportNote}
        />
      </div>
      {people.length === 0 ? (
        <EmptyState
          title={filtersActive ? "No hay coincidencias" : "Aún no hay personas"}
          hint={
            filtersActive
              ? "Prueba quitar filtros o ampliar la búsqueda (mínimo 2 caracteres)."
              : "Ejecuta la carga de documentos para poblar el archivo."
          }
        />
      ) : (
        <ul className="personas-screen-list divide-y divide-border overflow-hidden rounded-3xl border border-border bg-card shadow-sm print:hidden">
          {people.map((person) => {
            const incomplete = isIncompleteName(person.full_name, person.identity_number);
            const gaps = hasContactGaps(person.contact_gap);
            return (
              <li key={person.id}>
                <Link
                  href={`/personas/${person.id}`}
                  className="flex flex-wrap items-center justify-between gap-3 px-4 py-3.5 transition-colors hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring sm:px-5"
                >
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-foreground">
                        {person.full_name || "Sin nombre"}
                      </span>
                      {incomplete ? (
                        <span className="rounded-full bg-warning-soft px-2 py-0.5 text-[11px] font-medium text-warning">
                          Nombre incompleto
                        </span>
                      ) : null}
                      {gaps ? (
                        <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                          Contacto incompleto
                        </span>
                      ) : null}
                    </div>
                    <div className="text-xs text-muted-foreground">{personSummary(person)}</div>
                    <div className="flex flex-wrap gap-1.5 pt-0.5">
                      {person.titular_n > 0 ? (
                        <span className="rounded-full bg-hero px-2.5 py-0.5 text-[11px] font-medium text-white">
                          {roleCountLabel(ROLE_LABELS.titular, person.titular_n)}
                        </span>
                      ) : null}
                      {person.beneficiario_n > 0 ? (
                        <span className="rounded-full bg-brand/10 px-2.5 py-0.5 text-[11px] font-medium text-brand">
                          {roleCountLabel(ROLE_LABELS.beneficiario, person.beneficiario_n)}
                        </span>
                      ) : null}
                      {person.titular_n === 0 && person.beneficiario_n === 0 ? (
                        <span className="rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                          Sin rol en facturas
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <div className="shrink-0 text-xs tabular-nums text-muted-foreground">
                    {formatDocumentCount(person.docs)}
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}

      {exportPeople.length > 0 ? (
        <div className="personas-print-table hidden print:block">
          <h2 className="mb-3 text-base font-semibold text-foreground">Personas</h2>
          {exportCapped ? (
            <p className="mb-2 text-xs text-muted-foreground">
              Mostrando las primeras {PERSONAS_EXPORT_LIMIT.toLocaleString("es-VE")} de{" "}
              {total.toLocaleString("es-VE")} coincidencias.
            </p>
          ) : null}
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-border">
                <th className="py-1.5 pr-2 font-medium">Nombre</th>
                <th className="py-1.5 pr-2 font-medium">CI</th>
                <th className="py-1.5 pr-2 font-medium">Teléfono</th>
                <th className="py-1.5 pr-2 font-medium">Nacimiento</th>
                <th className="py-1.5 pr-2 font-medium">Titular</th>
                <th className="py-1.5 pr-2 font-medium">Beneficiario</th>
                <th className="py-1.5 font-medium">Documentos</th>
              </tr>
            </thead>
            <tbody>
              {exportPeople.map((person) => (
                <tr key={person.id} className="border-b border-border/70">
                  <td className="py-1.5 pr-2">{person.full_name || "Sin nombre"}</td>
                  <td className="py-1.5 pr-2 tabular-nums">
                    {person.identity_number?.trim() || "Sin cédula"}
                  </td>
                  <td className="py-1.5 pr-2 tabular-nums">{person.phone?.trim() || "Sin teléfono"}</td>
                  <td className="py-1.5 pr-2 tabular-nums">
                    {person.birth_date ? formatDateEs(person.birth_date) : "Sin fecha"}
                  </td>
                  <td className="py-1.5 pr-2 tabular-nums">{person.titular_n}</td>
                  <td className="py-1.5 pr-2 tabular-nums">{person.beneficiario_n}</td>
                  <td className="py-1.5 tabular-nums">{person.docs}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="personas-pagination print:hidden">
        <Pagination
          page={page}
          pageSize={DEFAULT_PAGE_SIZE}
          total={total}
          shown={people.length}
          basePath="/personas"
          searchParams={filterParams}
          hash="lista"
        />
      </div>
    </div>
  );
}
