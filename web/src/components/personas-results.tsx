import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { ListExportBar } from "@/components/list-export-bar";
import {
  Pagination,
  DEFAULT_PAGE_SIZE,
  clampPage,
  parsePage,
} from "@/components/pagination";
import { ResultCount } from "@/components/result-count";
import type { CsvTable } from "@/lib/csv";
import { ROLE_LABELS, sql } from "@/lib/db";
import { isIncompleteName } from "@/lib/persona-data";
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
  has_invoice?: string;
  has_contact_gap?: string;
  incomplete_name?: string;
  role?: string;
  account?: string;
  page?: string;
};

type PersonaListRow = {
  id: string;
  identity_type: string;
  identity_number: string | null;
  full_name: string | null;
  phone: string | null;
  birth_date: string | Date | null;
  contact_gap: unknown;
  docs: number;
  titular_n: number;
  beneficiario_n: number;
};

function yesNo(value: boolean): string {
  return value ? "sí" : "no";
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
        person.birth_date ? String(person.birth_date).slice(0, 10) : "",
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
  const hasInvoice = triState(sp.has_invoice);
  const hasContactGap = triState(sp.has_contact_gap);
  const incompleteName = triState(sp.incomplete_name);
  const role = firstParam(sp.role);
  const account = firstParam(sp.account);
  const requestedPage = parsePage(firstParam(sp.page) || undefined);
  const db = sql();

  const like = `%${query}%`;
  const roleOk = role === "titular" || role === "beneficiario" || role === "unknown";
  const roleFilter = roleOk ? role : "";
  const filtersActive = hasActiveFilters({
    q: query || undefined,
    has_ci: hasCi || undefined,
    has_phone: hasPhone || undefined,
    has_invoice: hasInvoice || undefined,
    has_contact_gap: hasContactGap || undefined,
    incomplete_name: incompleteName || undefined,
    role: roleFilter || undefined,
    account: account || undefined,
  });

  const [countRow] = await db`
    SELECT count(DISTINCT p.id)::int AS n
    FROM avila.person p
    LEFT JOIN avila.authorization_line al ON al.person_id = p.id
    LEFT JOIN avila.invoice_person ip ON ip.person_id = p.id
    LEFT JOIN avila.invoice i ON i.id = ip.invoice_id
    LEFT JOIN avila.account a ON a.id = i.account_id
    WHERE (${query} = '' OR p.identity_number ILIKE ${like}
           OR coalesce(p.full_name, '') ILIKE ${like}
           OR coalesce(p.phone, '') ILIKE ${like}
           OR coalesce(al.clave_rms, '') ILIKE ${like})
      AND (${hasCi} = '' OR (${hasCi} = '1' AND p.identity_number IS NOT NULL AND p.identity_number <> '')
           OR (${hasCi} = '0' AND (p.identity_number IS NULL OR p.identity_number = '')))
      AND (${hasPhone} = '' OR (${hasPhone} = '1' AND p.phone IS NOT NULL AND p.phone <> '')
           OR (${hasPhone} = '0' AND (p.phone IS NULL OR p.phone = '')))
      AND (${hasInvoice} = '' OR (${hasInvoice} = '1' AND EXISTS (
             SELECT 1 FROM avila.invoice_person ipx WHERE ipx.person_id = p.id
           ))
           OR (${hasInvoice} = '0' AND NOT EXISTS (
             SELECT 1 FROM avila.invoice_person ipx WHERE ipx.person_id = p.id
           )))
      AND (${hasContactGap} = '' OR (${hasContactGap} = '1' AND p.contact_gap IS NOT NULL
           AND (
             coalesce(p.contact_gap->>'birth_date', 'filled') <> 'filled'
             OR coalesce(p.contact_gap->>'phone', 'filled') <> 'filled'
             OR coalesce(p.contact_gap->>'address', 'filled') <> 'filled'
           )))
      AND (${incompleteName} = '' OR (${incompleteName} = '1' AND (
             coalesce(nullif(trim(p.full_name), ''), '') = ''
             OR (
               p.identity_number IS NOT NULL
               AND regexp_replace(coalesce(p.full_name, ''), '\\D', '', 'g')
                 = regexp_replace(p.identity_number, '\\D', '', 'g')
               AND p.full_name ~ '[0-9]'
             )
           )))
      AND (${roleFilter} = '' OR ip.role::text = ${roleFilter})
      AND (${account} = '' OR a.code = ${account})
  `;
  const total = countRow?.n ?? 0;
  const page = clampPage(requestedPage, total, DEFAULT_PAGE_SIZE);
  const offset = (page - 1) * DEFAULT_PAGE_SIZE;

  // Page and export share filters; run in parallel (export omits OFFSET, uses its own LIMIT).
  const [peoplePage, exportPage] = await Promise.all([
    db`
      SELECT p.id, p.identity_type::text AS identity_type, p.identity_number, p.full_name,
             p.phone, p.birth_date, p.contact_gap,
             coalesce(dc.docs, 0)::int AS docs,
             coalesce(roles.titular_n, 0)::int AS titular_n,
             coalesce(roles.beneficiario_n, 0)::int AS beneficiario_n
      FROM avila.person p
      LEFT JOIN (
        SELECT person_id, count(*)::int AS docs FROM avila.document GROUP BY person_id
      ) dc ON dc.person_id = p.id
      LEFT JOIN (
        SELECT person_id,
               count(DISTINCT invoice_id) FILTER (WHERE role = 'titular')::int AS titular_n,
               count(DISTINCT invoice_id) FILTER (WHERE role = 'beneficiario')::int AS beneficiario_n
        FROM avila.invoice_person
        GROUP BY person_id
      ) roles ON roles.person_id = p.id
      WHERE p.id IN (
        SELECT DISTINCT p2.id
        FROM avila.person p2
        LEFT JOIN avila.authorization_line al ON al.person_id = p2.id
        LEFT JOIN avila.invoice_person ip ON ip.person_id = p2.id
        LEFT JOIN avila.invoice i ON i.id = ip.invoice_id
        LEFT JOIN avila.account a ON a.id = i.account_id
        WHERE (${query} = '' OR p2.identity_number ILIKE ${like}
               OR coalesce(p2.full_name, '') ILIKE ${like}
               OR coalesce(p2.phone, '') ILIKE ${like}
               OR coalesce(al.clave_rms, '') ILIKE ${like})
          AND (${hasCi} = '' OR (${hasCi} = '1' AND p2.identity_number IS NOT NULL AND p2.identity_number <> '')
               OR (${hasCi} = '0' AND (p2.identity_number IS NULL OR p2.identity_number = '')))
          AND (${hasPhone} = '' OR (${hasPhone} = '1' AND p2.phone IS NOT NULL AND p2.phone <> '')
               OR (${hasPhone} = '0' AND (p2.phone IS NULL OR p2.phone = '')))
          AND (${hasInvoice} = '' OR (${hasInvoice} = '1' AND EXISTS (
                 SELECT 1 FROM avila.invoice_person ipx WHERE ipx.person_id = p2.id
               ))
               OR (${hasInvoice} = '0' AND NOT EXISTS (
                 SELECT 1 FROM avila.invoice_person ipx WHERE ipx.person_id = p2.id
               )))
          AND (${hasContactGap} = '' OR (${hasContactGap} = '1' AND p2.contact_gap IS NOT NULL
               AND (
                 coalesce(p2.contact_gap->>'birth_date', 'filled') <> 'filled'
                 OR coalesce(p2.contact_gap->>'phone', 'filled') <> 'filled'
                 OR coalesce(p2.contact_gap->>'address', 'filled') <> 'filled'
               )))
          AND (${incompleteName} = '' OR (${incompleteName} = '1' AND (
                 coalesce(nullif(trim(p2.full_name), ''), '') = ''
                 OR (
                   p2.identity_number IS NOT NULL
                   AND regexp_replace(coalesce(p2.full_name, ''), '\\D', '', 'g')
                     = regexp_replace(p2.identity_number, '\\D', '', 'g')
                   AND p2.full_name ~ '[0-9]'
                 )
               )))
          AND (${roleFilter} = '' OR ip.role::text = ${roleFilter})
          AND (${account} = '' OR a.code = ${account})
      )
      ORDER BY lower(nullif(trim(p.full_name), '')) ASC NULLS LAST,
               p.identity_number NULLS LAST,
               p.created_at DESC
      LIMIT ${DEFAULT_PAGE_SIZE} OFFSET ${offset}
    `,
    db`
      SELECT p.id, p.identity_type::text AS identity_type, p.identity_number, p.full_name,
             p.phone, p.birth_date, p.contact_gap,
             coalesce(dc.docs, 0)::int AS docs,
             coalesce(roles.titular_n, 0)::int AS titular_n,
             coalesce(roles.beneficiario_n, 0)::int AS beneficiario_n
      FROM avila.person p
      LEFT JOIN (
        SELECT person_id, count(*)::int AS docs FROM avila.document GROUP BY person_id
      ) dc ON dc.person_id = p.id
      LEFT JOIN (
        SELECT person_id,
               count(DISTINCT invoice_id) FILTER (WHERE role = 'titular')::int AS titular_n,
               count(DISTINCT invoice_id) FILTER (WHERE role = 'beneficiario')::int AS beneficiario_n
        FROM avila.invoice_person
        GROUP BY person_id
      ) roles ON roles.person_id = p.id
      WHERE p.id IN (
        SELECT DISTINCT p2.id
        FROM avila.person p2
        LEFT JOIN avila.authorization_line al ON al.person_id = p2.id
        LEFT JOIN avila.invoice_person ip ON ip.person_id = p2.id
        LEFT JOIN avila.invoice i ON i.id = ip.invoice_id
        LEFT JOIN avila.account a ON a.id = i.account_id
        WHERE (${query} = '' OR p2.identity_number ILIKE ${like}
               OR coalesce(p2.full_name, '') ILIKE ${like}
               OR coalesce(p2.phone, '') ILIKE ${like}
               OR coalesce(al.clave_rms, '') ILIKE ${like})
          AND (${hasCi} = '' OR (${hasCi} = '1' AND p2.identity_number IS NOT NULL AND p2.identity_number <> '')
               OR (${hasCi} = '0' AND (p2.identity_number IS NULL OR p2.identity_number = '')))
          AND (${hasPhone} = '' OR (${hasPhone} = '1' AND p2.phone IS NOT NULL AND p2.phone <> '')
               OR (${hasPhone} = '0' AND (p2.phone IS NULL OR p2.phone = '')))
          AND (${hasInvoice} = '' OR (${hasInvoice} = '1' AND EXISTS (
                 SELECT 1 FROM avila.invoice_person ipx WHERE ipx.person_id = p2.id
               ))
               OR (${hasInvoice} = '0' AND NOT EXISTS (
                 SELECT 1 FROM avila.invoice_person ipx WHERE ipx.person_id = p2.id
               )))
          AND (${hasContactGap} = '' OR (${hasContactGap} = '1' AND p2.contact_gap IS NOT NULL
               AND (
                 coalesce(p2.contact_gap->>'birth_date', 'filled') <> 'filled'
                 OR coalesce(p2.contact_gap->>'phone', 'filled') <> 'filled'
                 OR coalesce(p2.contact_gap->>'address', 'filled') <> 'filled'
               )))
          AND (${incompleteName} = '' OR (${incompleteName} = '1' AND (
                 coalesce(nullif(trim(p2.full_name), ''), '') = ''
                 OR (
                   p2.identity_number IS NOT NULL
                   AND regexp_replace(coalesce(p2.full_name, ''), '\\D', '', 'g')
                     = regexp_replace(p2.identity_number, '\\D', '', 'g')
                   AND p2.full_name ~ '[0-9]'
                 )
               )))
          AND (${roleFilter} = '' OR ip.role::text = ${roleFilter})
          AND (${account} = '' OR a.code = ${account})
      )
      ORDER BY lower(nullif(trim(p.full_name), '')) ASC NULLS LAST,
               p.identity_number NULLS LAST,
               p.created_at DESC
      LIMIT ${PERSONAS_EXPORT_LIMIT}
    `,
  ]);
  const people = peoplePage as PersonaListRow[];
  const exportPeople = exportPage as PersonaListRow[];

  const filterParams: Record<string, string | undefined> = {
    q: query || undefined,
    has_ci: hasCi || undefined,
    has_phone: hasPhone || undefined,
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
                        {person.full_name || "Sin nombre en OCR"}
                      </span>
                      {incomplete ? (
                        <span className="rounded-full bg-warning-soft px-2 py-0.5 text-[11px] font-medium text-warning">
                          Nombre incompleto
                        </span>
                      ) : null}
                      {gaps ? (
                        <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                          Gaps de contacto
                        </span>
                      ) : null}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {[
                        `${person.identity_type}: ${person.identity_number || "—"}`,
                        person.phone || null,
                        person.birth_date ? String(person.birth_date).slice(0, 10) : null,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </div>
                    <div className="flex flex-wrap gap-1.5 pt-0.5">
                      {person.titular_n > 0 ? (
                        <span className="rounded-full bg-hero px-2.5 py-0.5 text-[11px] font-medium text-white">
                          {`${ROLE_LABELS.titular} · ${person.titular_n}`}
                        </span>
                      ) : null}
                      {person.beneficiario_n > 0 ? (
                        <span className="rounded-full bg-brand/10 px-2.5 py-0.5 text-[11px] font-medium text-brand">
                          {`${ROLE_LABELS.beneficiario} · ${person.beneficiario_n}`}
                        </span>
                      ) : null}
                      {person.titular_n === 0 && person.beneficiario_n === 0 ? (
                        <span className="rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                          {ROLE_LABELS.unknown}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <div className="shrink-0 text-xs tabular-nums text-muted-foreground">
                    {person.docs} doc{person.docs === 1 ? "" : "s"}
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
                <th className="py-1.5 font-medium">Docs</th>
              </tr>
            </thead>
            <tbody>
              {exportPeople.map((person) => (
                <tr key={person.id} className="border-b border-border/70">
                  <td className="py-1.5 pr-2">{person.full_name || "Sin nombre en OCR"}</td>
                  <td className="py-1.5 pr-2 tabular-nums">
                    {person.identity_number || "—"}
                  </td>
                  <td className="py-1.5 pr-2 tabular-nums">{person.phone || "—"}</td>
                  <td className="py-1.5 pr-2 tabular-nums">
                    {person.birth_date ? String(person.birth_date).slice(0, 10) : "—"}
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
