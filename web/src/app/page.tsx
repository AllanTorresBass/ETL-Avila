import Link from "next/link";
import { Search } from "lucide-react";
import { AttentionPanel, type AttentionItem } from "@/components/attention-panel";
import { Meter } from "@/components/meter";
import { StatCard } from "@/components/stat-card";
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
  const [kpi] = await db`
    SELECT
      (SELECT count(*)::int FROM avila.authorization_line) AS auth_lines,
      (SELECT count(*)::int FROM avila.authorization_line WHERE invoice_id IS NOT NULL) AS auth_linked,
      (SELECT count(DISTINCT ip.invoice_id)::int
         FROM avila.invoice_person ip JOIN avila.person p ON p.id = ip.person_id
         WHERE ip.role = 'titular' AND p.identity_type = 'cedula') AS invoices_ci_titular,
      (SELECT count(*)::int FROM avila.person p
         WHERE NOT EXISTS (SELECT 1 FROM avila.invoice_person ip WHERE ip.person_id = p.id)) AS persons_no_invoice,
      (SELECT count(*)::int FROM avila.review_item WHERE status = 'open') AS open_reviews,
      (SELECT count(*)::int FROM avila.source_file WHERE rule_id = 'scan_packet') AS scan_files,
      (SELECT count(*)::int FROM avila.invoice i
         WHERE NOT EXISTS (
           SELECT 1 FROM avila.invoice_person tip
           WHERE tip.invoice_id = i.id AND tip.role = 'titular'
         )) AS invoices_no_titular,
      (SELECT count(*)::int FROM avila.invoice i
         WHERE EXISTS (
           SELECT 1 FROM avila.invoice_person tip
           WHERE tip.invoice_id = i.id AND tip.role = 'titular'
         ) AND EXISTS (
           SELECT 1 FROM avila.invoice_person bip
           WHERE bip.invoice_id = i.id AND bip.role = 'beneficiario'
         )) AS invoices_with_beneficiario,
      (SELECT count(*)::int FROM avila.review_item
         WHERE status = 'open'
           AND kind IN ('ci_conflict', 'multiple_ci', 'workbook_titular')) AS open_role_reviews
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

  const n = (v: number) => v.toLocaleString("es-VE");
  const maxType = Math.max(1, ...byType.map((r) => r.n));
  const maxAccount = Math.max(1, ...byAccount.map((r) => r.n));

  const attention: AttentionItem[] = [
    {
      id: "failed",
      title: "Documentos con carga fallida en Blob",
      hint: "Revisa la ruta de origen y vuelve a subirlos.",
      count: counts.failed,
      href: "/documentos?upload_status=failed",
      tone: "danger",
    },
    {
      id: "roles",
      title: "Casos de rol por resolver",
      hint: "Conflictos de cédula, titular del libro o varias cédulas.",
      count: kpi.open_role_reviews,
      href: "/revision",
      tone: "warning",
    },
    {
      id: "reviews",
      title: "Casos abiertos en la cola de revisión",
      hint: "Incluye todos los tipos, no solo los de rol.",
      count: kpi.open_reviews,
      href: "/revision",
      tone: "warning",
    },
    {
      id: "no-titular",
      title: "Facturas sin titular",
      hint: "No se puede atribuir la factura a una persona.",
      count: kpi.invoices_no_titular,
      href: "/facturas",
      tone: "info",
    },
    {
      id: "no-invoice",
      title: "Personas sin facturas",
      hint: "Clientes registrados que aún no tienen documentos.",
      count: kpi.persons_no_invoice,
      href: "/personas",
      tone: "info",
    },
  ];

  return (
    <div className="space-y-8">
      <section className="rise-in rounded-3xl bg-hero px-6 py-8 text-hero-foreground shadow-sm sm:px-8 sm:py-10">
        <p className="text-sm font-medium tracking-[0.14em] text-[#9bd0ff] uppercase">Ávila GPS</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
          Inventario de facturas
        </h1>
        <p className="mt-3 max-w-2xl text-base text-hero-foreground/85 text-pretty">
          Busca una persona por nombre, cédula o RIF y abre sus facturas y documentos.
        </p>
        <form action="/personas" method="get" role="search" className="mt-6 flex max-w-xl flex-col gap-2 sm:flex-row">
          <label htmlFor="busqueda-global" className="sr-only">
            Buscar personas
          </label>
          <div className="relative flex-1">
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute top-1/2 left-4 size-4 -translate-y-1/2 text-muted-foreground"
            />
            <input
              id="busqueda-global"
              name="q"
              type="search"
              placeholder="Nombre, cédula o RIF"
              autoComplete="off"
              className="h-12 w-full rounded-full border border-transparent bg-card pr-4 pl-11 text-base text-foreground placeholder:text-muted-foreground"
            />
          </div>
          <button type="submit" className="btn-green-gradient h-12 rounded-full px-6 text-sm font-semibold">
            Buscar
          </button>
        </form>
        <p className="mt-4 text-sm text-hero-foreground/75">
          {n(counts.persons)} personas · {n(counts.invoices)} facturas · {n(counts.documents)} documentos
        </p>
      </section>

      <div className="rise-in" style={{ "--i": 1 } as React.CSSProperties}>
        <AttentionPanel items={attention} />
      </div>

      <section aria-label="Inventario" className="rise-in grid gap-4 sm:grid-cols-2 lg:grid-cols-4" style={{ "--i": 2 } as React.CSSProperties}>
        <StatCard label="Personas" value={counts.persons} href="/personas" />
        <StatCard label="Facturas" value={counts.invoices} href="/facturas" />
        <StatCard label="Documentos" value={counts.documents} href="/documentos" />
        <StatCard label="Archivos fuente" value={counts.source_files} hint={`${n(kpi.scan_files)} de escáner`} />
      </section>

      <section
        aria-labelledby="calidad-titulo"
        className="rise-in rounded-3xl border border-border bg-card p-5 shadow-sm sm:p-6"
        style={{ "--i": 3 } as React.CSSProperties}
      >
        <h2 id="calidad-titulo" className="text-lg font-semibold text-foreground">
          Calidad del vínculo
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">Qué tan completo está el cruce entre fuentes.</p>
        <div className="mt-5 grid gap-6 md:grid-cols-2">
          <Meter label="Autorizaciones con factura" value={kpi.auth_linked} total={kpi.auth_lines} />
          <Meter label="Facturas con titular por cédula" value={kpi.invoices_ci_titular} total={counts.invoices} />
          <Meter label="Facturas con beneficiario" value={kpi.invoices_with_beneficiario} total={counts.invoices} />
          <Meter
            label="Documentos subidos a Blob"
            value={counts.uploaded}
            total={counts.documents}
            href="/documentos?upload_status=failed"
          />
        </div>
      </section>

      <div className="rise-in grid gap-6 lg:grid-cols-2" style={{ "--i": 4 } as React.CSSProperties}>
        <BreakdownCard
          title="Por tipo de documento"
          empty="Aún no hay documentos cargados."
          rows={byType.map((row) => ({
            key: row.document_type,
            label: DOCUMENT_TYPE_LABELS[row.document_type] || row.document_type,
            n: row.n,
            href: `/documentos?type=${row.document_type}`,
          }))}
          max={maxType}
        />
        <BreakdownCard
          title="Facturas por cuenta"
          empty="Aún no hay facturas cargadas."
          rows={byAccount.map((row) => ({
            key: row.account_code || row.account,
            label: formatAccount(row.account),
            n: row.n,
            href: row.account_code ? `/facturas?account=${row.account_code}` : "/facturas",
          }))}
          max={maxAccount}
        />
      </div>
    </div>
  );
}

function BreakdownCard({
  title,
  rows,
  max,
  empty,
}: {
  title: string;
  rows: { key: string; label: string; n: number; href: string }[];
  max: number;
  empty: string;
}) {
  return (
    <Card className="rounded-3xl border-border shadow-sm">
      <CardHeader>
        <CardTitle className="text-lg font-semibold text-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">{empty}</p>
        ) : (
          <ul className="space-y-1">
            {rows.map((row) => (
              <li key={row.key}>
                <Link
                  href={row.href}
                  className="group block rounded-xl px-2 py-2 transition-colors hover:bg-muted"
                >
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="min-w-0 truncate font-medium text-foreground">{row.label}</span>
                    <span className="tabular-nums text-muted-foreground">{row.n.toLocaleString("es-VE")}</span>
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted group-hover:bg-card">
                    <div
                      className="h-full rounded-full bg-brand/70"
                      style={{ width: `${Math.max(2, Math.round((row.n / max) * 100))}%` }}
                    />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
