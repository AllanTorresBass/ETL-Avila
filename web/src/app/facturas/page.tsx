import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Pagination, DEFAULT_PAGE_SIZE, parsePage } from "@/components/pagination";
import { ResultCount } from "@/components/result-count";
import { sql } from "@/lib/db";
import { formatAccount, formatInvoiceNumber } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function FacturasPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; account?: string; page?: string }>;
}) {
  const { q = "", account = "", page: pageRaw } = await searchParams;
  const page = parsePage(pageRaw);
  const offset = (page - 1) * DEFAULT_PAGE_SIZE;
  const db = sql();
  const accounts = await db`SELECT code, legal_name FROM avila.account ORDER BY legal_name`;
  const query = q.trim();

  const [countRow] = await db`
    SELECT count(*)::int AS n
    FROM avila.invoice i
    LEFT JOIN avila.account a ON a.id = i.account_id
    WHERE (${query} = '' OR i.invoice_number ILIKE ${"%" + query + "%"})
      AND (${account} = '' OR a.code = ${account})
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
    ORDER BY i.invoice_number DESC
    LIMIT ${DEFAULT_PAGE_SIZE} OFFSET ${offset}
  `;

  return (
    <div className="space-y-6">
      <PageHeader title="Facturas" description="Directorio del universo inventariado." />
      <form className="flex flex-wrap items-end gap-2">
        <label className="block text-xs font-medium">
          Número
          <Input
            name="q"
            defaultValue={q}
            placeholder="Número de factura"
            className="mt-1 max-w-xs rounded-xl"
          />
        </label>
        <label className="block text-xs font-medium">
          Cuenta
          <select
            name="account"
            defaultValue={account}
            className="mt-1 block rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs"
          >
            <option value="">Todas las cuentas</option>
            {accounts.map((a) => (
              <option key={a.code} value={a.code}>
                {a.legal_name}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="btn-green-gradient rounded-full px-5 py-2.5 text-xs font-medium text-white">
          Filtrar
        </button>
      </form>
      <ResultCount shown={invoices.length} total={total} />
      {invoices.length === 0 ? (
        <EmptyState
          title="No se encontraron facturas"
          hint="Intenta cambiar el número o el filtro de cuenta."
        />
      ) : (
        <div className="grid gap-3">
          {invoices.map((inv) => (
            <Link key={inv.id} href={`/facturas/${inv.id}`}>
              <Card className="rounded-3xl border-slate-100 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">
                <CardContent className="flex flex-wrap items-center justify-between gap-3 p-5 text-sm">
                  <div>
                    <div className="font-medium">{formatInvoiceNumber(inv.invoice_number)}</div>
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
        searchParams={{ q: query || undefined, account: account || undefined }}
      />
    </div>
  );
}
