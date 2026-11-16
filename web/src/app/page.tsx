import Link from "next/link";
import { StatCard } from "@/components/stat-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DOCUMENT_TYPE_LABELS, sql } from "@/lib/db";
import { formatAccount } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const db = sql();
  const [counts] = await db`
    SELECT
      (SELECT count(*)::int FROM avila.person) AS persons,
      (SELECT count(*)::int FROM avila.invoice) AS invoices,
      (SELECT count(*)::int FROM avila.source_file) AS source_files,
      (SELECT count(*)::int FROM avila.document) AS documents,
      (SELECT count(*)::int FROM avila.document WHERE upload_status = 'uploaded') AS uploaded,
      (SELECT count(*)::int FROM avila.document WHERE upload_status = 'failed') AS failed
  `;
  const byType = await db`
    SELECT document_type::text AS document_type, count(*)::int AS n
    FROM avila.document
    GROUP BY 1
    ORDER BY n DESC
  `;
  const byAccount = await db`
    SELECT a.code AS account_code, coalesce(a.legal_name, '(sin cuenta)') AS account, count(*)::int AS n
    FROM avila.invoice i
    LEFT JOIN avila.account a ON a.id = i.account_id
    GROUP BY a.code, a.legal_name
    ORDER BY n DESC
    LIMIT 12
  `;

  return (
    <div className="space-y-8">
      <section className="rounded-3xl bg-[#0A2A6B] px-6 py-10 text-white shadow-sm sm:px-8">
        <p className="text-xs font-medium tracking-[0.14em] text-[#5BB2F5] uppercase">Ávila GPS</p>
        <h1 className="mt-2 text-3xl font-medium tracking-tight sm:text-4xl">Inventario de facturas</h1>
        <p className="mt-3 max-w-2xl text-sm font-light text-white/85">
          Personas como cliente, facturas del universo inventariado y cada página del paquete como un
          documento con enlace propio.
        </p>
        <div className="mt-6 flex flex-wrap gap-2">
          <Link href="/personas" className="btn-green-gradient rounded-full px-5 py-2.5 text-xs font-medium text-white">
            Ver personas
          </Link>
          <Link
            href="/facturas"
            className="rounded-full border border-white/40 bg-[#033CA0]/55 px-5 py-2.5 text-xs font-medium text-white backdrop-blur"
          >
            Ver facturas
          </Link>
          <Link
            href="/documentos"
            className="rounded-full border border-white/40 bg-[#033CA0]/55 px-5 py-2.5 text-xs font-medium text-white backdrop-blur"
          >
            Ver documentos
          </Link>
          {counts.failed > 0 ? (
            <Link
              href="/documentos?upload_status=failed"
              className="rounded-full border border-amber-300/60 bg-amber-500/20 px-5 py-2.5 text-xs font-medium text-white"
            >
              {counts.failed} fallidos en Blob
            </Link>
          ) : null}
        </div>
      </section>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Link href="/personas">
          <StatCard label="Personas" value={counts.persons} />
        </Link>
        <Link href="/facturas">
          <StatCard label="Facturas" value={counts.invoices} />
        </Link>
        <StatCard label="Archivos fuente" value={counts.source_files} />
        <Link href="/documentos">
          <StatCard label="Documentos" value={counts.documents} />
        </Link>
        <StatCard label="Subidos a Blob" value={counts.uploaded} />
        <Link href="/documentos?upload_status=failed">
          <StatCard label="Fallidos" value={counts.failed} />
        </Link>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="rounded-3xl border-slate-100 shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg font-medium text-[#0A2A6B]">Por tipo de documento</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {byType.length === 0 ? (
              <p className="text-sm text-slate-500">Aún no hay documentos cargados.</p>
            ) : (
              byType.map((row) => (
                <Link
                  key={row.document_type}
                  href={`/documentos?type=${row.document_type}`}
                  className="flex items-center justify-between gap-3 text-sm hover:text-[#033CA0]"
                >
                  <Badge variant="secondary" className="rounded-full">
                    {DOCUMENT_TYPE_LABELS[row.document_type] || row.document_type}
                  </Badge>
                  <span className="tabular-nums text-slate-600">{row.n.toLocaleString("es-VE")}</span>
                </Link>
              ))
            )}
          </CardContent>
        </Card>
        <Card className="rounded-3xl border-slate-100 shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg font-medium text-[#0A2A6B]">Facturas por cuenta</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {byAccount.length === 0 ? (
              <p className="text-sm text-slate-500">Aún no hay facturas cargadas.</p>
            ) : (
              byAccount.map((row) => (
                <Link
                  key={row.account_code || row.account}
                  href={row.account_code ? `/facturas?account=${row.account_code}` : "/facturas"}
                  className="flex items-center justify-between gap-3 text-sm hover:text-[#033CA0]"
                >
                  <span>{formatAccount(row.account)}</span>
                  <span className="tabular-nums text-slate-600">{row.n.toLocaleString("es-VE")}</span>
                </Link>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
