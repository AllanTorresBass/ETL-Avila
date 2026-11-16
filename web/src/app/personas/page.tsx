import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/empty-state";
import { ListFilterBar } from "@/components/list-filter-bar";
import { PageHeader } from "@/components/page-header";
import { Pagination, DEFAULT_PAGE_SIZE, parsePage } from "@/components/pagination";
import { ResultCount } from "@/components/result-count";
import { ROLE_LABELS, sql } from "@/lib/db";
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
  const role = firstParam(sp.role);
  const account = firstParam(sp.account);
  const page = parsePage(firstParam(sp.page) || undefined);
  const offset = (page - 1) * DEFAULT_PAGE_SIZE;
  const db = sql();

  const accounts = await db`SELECT code, legal_name FROM avila.account ORDER BY legal_name`;
  const like = `%${query}%`;
  const roleOk = role === "titular" || role === "beneficiario" || role === "unknown";
  const roleFilter = roleOk ? role : "";

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
      AND (${roleFilter} = '' OR ip.role::text = ${roleFilter})
      AND (${account} = '' OR a.code = ${account})
  `;
  const total = countRow?.n ?? 0;

  const people = await db`
    SELECT p.id, p.identity_type::text AS identity_type, p.identity_number, p.full_name,
           p.phone, p.birth_date,
           coalesce(dc.docs, 0)::int AS docs
    FROM avila.person p
    LEFT JOIN (
      SELECT person_id, count(*)::int AS docs FROM avila.document GROUP BY person_id
    ) dc ON dc.person_id = p.id
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

  const clearHref = hasActiveFilters(filterParams) ? "/personas" : undefined;

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
      <ResultCount shown={people.length} total={total} />
      {people.length === 0 ? (
        <EmptyState
          title="No se encontraron personas"
          hint="Intenta cambiar los filtros o ejecuta la carga de documentos."
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {people.map((person) => (
            <Link key={person.id} href={`/personas/${person.id}`}>
              <Card className="rounded-3xl border-slate-100 shadow-sm transition hover:-translate-y-1 hover:shadow-lg">
                <CardContent className="p-5">
                  <div className="text-sm font-medium">
                    {person.full_name || "Sin nombre en OCR"}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {person.identity_type}: {person.identity_number || "—"}
                  </div>
                  {(person.phone || person.birth_date) && (
                    <div className="mt-1 text-xs text-slate-500">
                      {person.phone || "Sin teléfono"}
                      {person.birth_date
                        ? ` · ${String(person.birth_date).slice(0, 10)}`
                        : ""}
                    </div>
                  )}
                  <div className="mt-3 text-xs text-[#033CA0]">
                    {person.docs} documentos de identidad
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
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
