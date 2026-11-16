import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/empty-state";
import { ListFilterBar } from "@/components/list-filter-bar";
import { PageHeader } from "@/components/page-header";
import { Pagination, DEFAULT_PAGE_SIZE, parsePage } from "@/components/pagination";
import { ResultCount } from "@/components/result-count";
import { sql } from "@/lib/db";
import { formatAccount, formatInvoiceNumber } from "@/lib/format";
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

export default async function FacturasPage({
  searchParams,
}: {
  searchParams: Promise<{
    q?: string;
    account?: string;
    year?: string;
    month?: string;
    has_person?: string;
    page?: string;
  }>;
}) {
  const sp = await searchParams;
  const query = normalizeQuery(sp.q);
  const rawQ = firstParam(sp.q);
  const account = firstParam(sp.account);
  const year = firstParam(sp.year);
  const month = firstParam(sp.month);
  const hasPerson = triState(sp.has_person);
  const page = parsePage(firstParam(sp.page) || undefined);
  const offset = (page - 1) * DEFAULT_PAGE_SIZE;
  const db = sql();

  const accounts = await db`SELECT code, legal_name FROM avila.account ORDER BY legal_name`;
  const years = await db`
    SELECT DISTINCT year AS y FROM avila.invoice
    WHERE year IS NOT NULL AND year <> ''
    ORDER BY year DESC
  `;
  const months = await db`
    SELECT DISTINCT month AS m FROM avila.invoice
    WHERE month IS NOT NULL AND month <> ''
    ORDER BY month
  `;

  const [countRow] = await db`
    SELECT count(*)::int AS n
    FROM avila.invoice i
    LEFT JOIN avila.account a ON a.id = i.account_id
    WHERE (${query} = '' OR i.invoice_number ILIKE ${"%" + query + "%"})
      AND (${account} = '' OR a.code = ${account})
      AND (${year} = '' OR i.year = ${year})
      AND (${month} = '' OR i.month = ${month})
      AND (${hasPerson} = '' OR (${hasPerson} = '1' AND EXISTS (
            SELECT 1 FROM avila.invoice_person ip WHERE ip.invoice_id = i.id
          )) OR (${hasPerson} = '0' AND NOT EXISTS (
            SELECT 1 FROM avila.invoice_person ip WHERE ip.invoice_id = i.id
          )))
  `;
  const total = countRow?.n ?? 0;

  const invoices = await db`
    SELECT i.id, i.invoice_number, i.year, i.month, i.lote, a.legal_name AS account,
           coalesce(dc.docs, 0)::int AS docs
    FROM avila.invoice i
    LEFT JOIN avila.account a ON a.id = i.account_id
    LEFT JOIN (
      SELECT invoice_id, count(*)::int AS docs FROM avila.document GROUP BY invoice_id
    ) dc ON dc.invoice_id = i.id
    WHERE (${query} = '' OR i.invoice_number ILIKE ${"%" + query + "%"})
      AND (${account} = '' OR a.code = ${account})
      AND (${year} = '' OR i.year = ${year})
      AND (${month} = '' OR i.month = ${month})
      AND (${hasPerson} = '' OR (${hasPerson} = '1' AND EXISTS (
            SELECT 1 FROM avila.invoice_person ip WHERE ip.invoice_id = i.id
          )) OR (${hasPerson} = '0' AND NOT EXISTS (
            SELECT 1 FROM avila.invoice_person ip WHERE ip.invoice_id = i.id
          )))
    ORDER BY i.invoice_number DESC
    LIMIT ${DEFAULT_PAGE_SIZE} OFFSET ${offset}
  `;

  const filterParams: Record<string, string | undefined> = {
    q: query || undefined,
    account: account || undefined,
    year: year || undefined,
    month: month || undefined,
    has_person: hasPerson || undefined,
  };

  const activeChips: ActiveChip[] = [];
  if (query) {
    activeChips.push({
      key: "q",
      label: `Nº ${query}`,
      clearHref: buildListHref("/facturas", omitParam(filterParams, "q")),
    });
  }
  if (account) {
    const accName = accounts.find((a) => a.code === account)?.legal_name || account;
    activeChips.push({
      key: "account",
      label: accName,
      clearHref: buildListHref("/facturas", omitParam(filterParams, "account")),
    });
  }
  if (year) {
    activeChips.push({
      key: "year",
      label: `Año ${year}`,
      clearHref: buildListHref("/facturas", omitParam(filterParams, "year")),
    });
  }
  if (month) {
    activeChips.push({
      key: "month",
      label: `Mes ${month}`,
      clearHref: buildListHref("/facturas", omitParam(filterParams, "month")),
    });
  }
  if (hasPerson === "1") {
    activeChips.push({
      key: "has_person",
      label: "Con persona",
      clearHref: buildListHref("/facturas", omitParam(filterParams, "has_person")),
    });
  } else if (hasPerson === "0") {
    activeChips.push({
      key: "has_person",
      label: "Sin persona",
      clearHref: buildListHref("/facturas", omitParam(filterParams, "has_person")),
    });
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Facturas" description="Directorio del universo inventariado." />
      <ListFilterBar
        searchValue={rawQ}
        searchPlaceholder="Número de factura (mín. 2)"
        searchLabel="Número"
        submitLabel="Filtrar"
        clearHref={hasActiveFilters(filterParams) ? "/facturas" : undefined}
        activeChips={activeChips}
        selects={[
          {
            name: "account",
            label: "Cuenta",
            value: account,
            emptyLabel: "Todas las cuentas",
            options: accounts.map((a) => ({ value: a.code, label: a.legal_name })),
          },
          {
            name: "year",
            label: "Año",
            value: year,
            emptyLabel: "Todos",
            options: years
              .filter((r) => r.y)
              .map((r) => ({ value: String(r.y), label: String(r.y) })),
          },
          {
            name: "month",
            label: "Mes",
            value: month,
            emptyLabel: "Todos",
            options: months
              .filter((r) => r.m)
              .map((r) => ({ value: String(r.m), label: String(r.m) })),
          },
          {
            name: "has_person",
            label: "Persona",
            value: hasPerson,
            emptyLabel: "Todas",
            options: [
              { value: "1", label: "Con persona" },
              { value: "0", label: "Sin persona" },
            ],
          },
        ]}
      />
      <ResultCount shown={invoices.length} total={total} />
      {invoices.length === 0 ? (
        <EmptyState
          title="No se encontraron facturas"
          hint="Intenta cambiar el número, la cuenta o el periodo."
        />
      ) : (
        <div className="grid gap-3">
          {invoices.map((inv) => (
            <Link key={inv.id} href={`/facturas/${inv.id}`}>
              <Card className="rounded-3xl border-slate-100 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">
                <CardContent className="flex flex-wrap items-center justify-between gap-3 p-5 text-sm">
                  <div>
                    <div className="font-medium">
                      {formatInvoiceNumber(inv.invoice_number)}
                    </div>
                    <div className="text-xs text-slate-500">
                      {formatAccount(inv.account)} · {inv.month || "—"} {inv.year || ""} · lote{" "}
                      {inv.lote || "—"}
                    </div>
                  </div>
                  <div className="text-xs text-[#033CA0]">{inv.docs} páginas</div>
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
        basePath="/facturas"
        searchParams={filterParams}
      />
    </div>
  );
}
