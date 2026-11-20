import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { ListFilterBar } from "@/components/list-filter-bar";
import { PageHeader } from "@/components/page-header";
import { Pagination, DEFAULT_PAGE_SIZE, parsePage } from "@/components/pagination";
import { ResultCount } from "@/components/result-count";
import { ROLE_LABELS, sql } from "@/lib/db";
import { isIncompleteName } from "@/lib/persona-data";
import {
  buildListHref,
  firstParam,
  hasActiveFilters,
  normalizeQuery,
  omitParam,
  triState,
  type ActiveChip,
} from "@/lib/list-params";

export const dynamic = "force-dynamic";

export default async function PersonasPage({
  searchParams,
}: {
  searchParams: Promise<{
    q?: string;
    has_ci?: string;
    has_phone?: string;
    has_invoice?: string;
    role?: string;
    account?: string;
    page?: string;
  }>;
}) {
  const sp = await searchParams;
  const query = normalizeQuery(sp.q);
  const rawQ = firstParam(sp.q);
  const hasCi = triState(sp.has_ci);
  const hasPhone = triState(sp.has_phone);
  const hasInvoice = triState(sp.has_invoice);
  const role = firstParam(sp.role);
  const account = firstParam(sp.account);
  const page = parsePage(firstParam(sp.page) || undefined);
  const offset = (page - 1) * DEFAULT_PAGE_SIZE;
  const db = sql();

  const accounts = await db`SELECT code, legal_name FROM avila.account ORDER BY legal_name`;
  const like = `%${query}%`;
  const roleOk = role === "titular" || role === "beneficiario" || role === "unknown";
  const roleFilter = roleOk ? role : "";
  const filtersActive = hasActiveFilters({
    q: query || undefined,
    has_ci: hasCi || undefined,
    has_phone: hasPhone || undefined,
    has_invoice: hasInvoice || undefined,
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
      AND (${roleFilter} = '' OR ip.role::text = ${roleFilter})
      AND (${account} = '' OR a.code = ${account})
  `;
  const total = countRow?.n ?? 0;

  const people = await db`
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
        AND (${roleFilter} = '' OR ip.role::text = ${roleFilter})
        AND (${account} = '' OR a.code = ${account})
    )
    ORDER BY lower(nullif(trim(p.full_name), '')) ASC NULLS LAST,
             p.identity_number NULLS LAST,
             p.created_at DESC
    LIMIT ${DEFAULT_PAGE_SIZE} OFFSET ${offset}
  `;

  const filterParams: Record<string, string | undefined> = {
    q: query || undefined,
    has_ci: hasCi || undefined,
    has_phone: hasPhone || undefined,
    has_invoice: hasInvoice || undefined,
    role: roleFilter || undefined,
    account: account || undefined,
  };

  const activeChips: ActiveChip[] = [];
  if (query) {
    activeChips.push({
      key: "q",
      label: `Buscar: ${query}`,
      clearHref: buildListHref("/personas", omitParam(filterParams, "q")),
    });
  }
  if (hasCi === "1") {
    activeChips.push({
      key: "has_ci",
      label: "Con cédula",
      clearHref: buildListHref("/personas", omitParam(filterParams, "has_ci")),
    });
  } else if (hasCi === "0") {
    activeChips.push({
      key: "has_ci",
      label: "Sin cédula",
      clearHref: buildListHref("/personas", omitParam(filterParams, "has_ci")),
    });
  }
  if (hasPhone === "1") {
    activeChips.push({
      key: "has_phone",
      label: "Con teléfono",
      clearHref: buildListHref("/personas", omitParam(filterParams, "has_phone")),
    });
  } else if (hasPhone === "0") {
    activeChips.push({
      key: "has_phone",
      label: "Sin teléfono",
      clearHref: buildListHref("/personas", omitParam(filterParams, "has_phone")),
    });
  }
  if (hasInvoice === "1") {
    activeChips.push({
      key: "has_invoice",
      label: "Con factura",
      clearHref: buildListHref("/personas", omitParam(filterParams, "has_invoice")),
    });
  } else if (hasInvoice === "0") {
    activeChips.push({
      key: "has_invoice",
      label: "Sin factura",
      clearHref: buildListHref("/personas", omitParam(filterParams, "has_invoice")),
    });
  }
  if (roleFilter) {
    activeChips.push({
      key: "role",
      label: ROLE_LABELS[roleFilter] || roleFilter,
      clearHref: buildListHref("/personas", omitParam(filterParams, "role")),
    });
  }
  if (account) {
    const accName = accounts.find((a) => a.code === account)?.legal_name || account;
    activeChips.push({
      key: "account",
      label: accName,
      clearHref: buildListHref("/personas", omitParam(filterParams, "account")),
    });
  }

  const clearHref = filtersActive ? "/personas" : undefined;
  const shortQueryHint = rawQ.length === 1;

  function hasContactGaps(gap: unknown): boolean {
    if (!gap || typeof gap !== "object") return false;
    return Object.values(gap as Record<string, unknown>).some(
      (v) => typeof v === "string" && v !== "filled",
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Personas"
        description="Cliente = titular o beneficiario. Busca por cédula, nombre, teléfono o clave RMS."
      />
      <ListFilterBar
        searchValue={rawQ}
        searchPlaceholder="Cédula, nombre, teléfono o clave (mín. 2)"
        searchLabel="Buscar"
        submitLabel="Filtrar"
        clearHref={clearHref}
        activeChips={activeChips}
        selects={[
          {
            name: "has_ci",
            label: "Cédula",
            value: hasCi,
            emptyLabel: "Todas",
            options: [
              { value: "1", label: "Con cédula" },
              { value: "0", label: "Sin cédula" },
            ],
          },
          {
            name: "has_phone",
            label: "Teléfono",
            value: hasPhone,
            emptyLabel: "Todos",
            options: [
              { value: "1", label: "Con teléfono" },
              { value: "0", label: "Sin teléfono" },
            ],
          },
          {
            name: "has_invoice",
            label: "Factura",
            value: hasInvoice,
            emptyLabel: "Todas",
            options: [
              { value: "1", label: "Con factura" },
              { value: "0", label: "Sin factura" },
            ],
          },
          {
            name: "role",
            label: "Rol en factura",
            value: roleFilter,
            emptyLabel: "Todos los roles",
            options: [
              { value: "titular", label: ROLE_LABELS.titular },
              { value: "beneficiario", label: ROLE_LABELS.beneficiario },
              { value: "unknown", label: ROLE_LABELS.unknown },
            ],
          },
          {
            name: "account",
            label: "Cuenta",
            value: account,
            emptyLabel: "Todas las cuentas",
            options: accounts.map((a) => ({ value: a.code, label: a.legal_name })),
          },
        ]}
      />
      {shortQueryHint ? (
        <p role="status" className="text-sm text-muted-foreground">
          Escribe al menos 2 caracteres para buscar.
        </p>
      ) : null}
      <ResultCount shown={people.length} total={total} />
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
        <ul className="divide-y divide-border overflow-hidden rounded-3xl border border-border bg-card shadow-sm">
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
      <Pagination
        page={page}
        pageSize={DEFAULT_PAGE_SIZE}
        total={total}
        basePath="/personas"
        searchParams={filterParams}
      />
    </div>
  );
}
