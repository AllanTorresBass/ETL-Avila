import type { Metadata } from "next";
import Link from "next/link";
import { BadgeCheck, CircleDollarSign, Gauge, ReceiptText } from "lucide-react";
import { BreakdownCard } from "@/components/breakdown-card";
import { DashboardHeader } from "@/components/dashboard-header";
import { DashboardNotice } from "@/components/dashboard-notice";
import { DonutChart } from "@/components/donut-chart";
import { KpiCard } from "@/components/kpi-card";
import { Meter } from "@/components/meter";
import { SectionCard } from "@/components/section-card";
import { TrendChart } from "@/components/trend-chart";
import { BI_RANGES, getBiData, parseRange } from "@/lib/dashboard-data";
import { DOCUMENT_TYPE_LABELS } from "@/lib/db";
import { formatAccount } from "@/lib/format";
import { formatPercent, formatUsd, formatUsdCompact, percentChange } from "@/lib/format-metrics";

export const metadata: Metadata = {
  title: "Tablero de negocio · Ávila GPS",
  description: "Facturación, cuentas, proveedores y autorizaciones en un solo vistazo.",
};

export const dynamic = "force-dynamic";

const n = (v: number) => v.toLocaleString("es-VE");
const stagger = (i: number) => ({ "--i": i }) as React.CSSProperties;

function RangeTabs({ current }: { current: string }) {
  return (
    <nav aria-label="Periodo" className="inline-flex gap-1 rounded-full border border-border bg-card p-1 shadow-sm">
      {BI_RANGES.map((r) => {
        const active = r.id === current;
        return (
          <Link
            key={r.id}
            href={`/bi?rango=${r.id}`}
            aria-current={active ? "true" : undefined}
            scroll={false}
            className={`inline-flex min-h-9 items-center rounded-full px-3 text-sm font-medium transition-colors ${
              active ? "bg-brand text-primary-foreground" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {r.label}
          </Link>
        );
      })}
    </nav>
  );
}

export default async function BiDashboardPage({ searchParams }: PageProps<"/bi">) {
  const range = parseRange((await searchParams).rango);
  const data = await getBiData(range);
  const { totals, authorization } = data;
  const rangeLabel = BI_RANGES.find((r) => r.id === range)?.label ?? "";
  const comparable = data.months > 0;

  const usdDelta = comparable ? percentChange(totals.usd, data.previous.usd) : null;
  const invoiceDelta = comparable ? percentChange(totals.invoices, data.previous.invoices) : null;
  const authorizedShare = authorization.requestedUsd > 0 ? authorization.authorized / authorization.requestedUsd : 0;

  return (
    <div className="space-y-8">
      <div className="rise-in">
        <DashboardHeader
          current="bi"
          title="Inteligencia de negocio"
          description="Cuánto se factura, con quién y cómo evoluciona, a partir de los montos leídos en las facturas fiscales."
          actions={<RangeTabs current={range} />}
        />
      </div>

      <DashboardNotice failures={data.failures} />

      {totals.invoices > 0 && totals.usdCoverage < 0.9 ? (
        <p
          role="status"
          className="rise-in rounded-2xl border border-border bg-muted px-4 py-3 text-sm text-muted-foreground"
          style={stagger(1)}
        >
          Solo {formatPercent(totals.usdCoverage)} de las facturas del periodo tiene monto en USD leído (
          {n(totals.withUsd)} de {n(totals.invoices)}). Los totales de dinero reflejan únicamente esas facturas.
        </p>
      ) : null}

      <section aria-label="Indicadores clave" className="rise-in grid gap-4 sm:grid-cols-2 lg:grid-cols-4" style={stagger(1)}>
        <KpiCard
          featured
          label={`Facturado en USD · ${rangeLabel.toLowerCase()}`}
          value={formatUsdCompact(totals.usd)}
          hint={totals.usd > 0 ? formatUsd(totals.usd) : "Sin montos en el periodo"}
          delta={usdDelta}
          deltaLabel="frente al periodo anterior"
          icon={<CircleDollarSign className="size-4" />}
        />
        <KpiCard
          label="Facturas emitidas"
          value={n(totals.invoices)}
          delta={invoiceDelta}
          hint={comparable ? "vs. periodo anterior" : undefined}
          href="/facturas"
          icon={<ReceiptText className="size-4" />}
        />
        <KpiCard
          label="Ticket promedio"
          value={totals.withUsd > 0 ? formatUsd(totals.averageUsd) : "—"}
          hint={totals.maxUsd > 0 ? `Máx. ${formatUsd(totals.maxUsd)}` : undefined}
          icon={<Gauge className="size-4" />}
        />
        <KpiCard
          label="Autorizado sobre solicitado"
          value={authorization.requestedUsd > 0 ? formatPercent(authorizedShare) : "—"}
          hint={`${formatUsdCompact(authorization.authorized)} de ${formatUsdCompact(authorization.requestedUsd)}`}
          icon={<BadgeCheck className="size-4" />}
        />
      </section>

      <SectionCard
        className="rise-in"
        title="Evolución mensual"
        description="Monto facturado y número de facturas por mes de emisión."
      >
        <TrendChart data={data.monthly} />
      </SectionCard>

      <div className="rise-in grid gap-6 lg:grid-cols-2" style={stagger(3)}>
        <BreakdownCard
          title="Principales cuentas"
          description="Ordenadas por monto facturado en USD."
          rows={data.byAccount.map((a) => ({
            key: a.code ?? a.name,
            label: formatAccount(a.name),
            value: a.usd > 0 ? a.usd : a.invoices,
            display: a.usd > 0 ? formatUsdCompact(a.usd) : "—",
            hint: `${n(a.invoices)} fact.`,
            href: a.code ? `/facturas?account=${a.code}` : "/facturas",
          }))}
          empty="Sin facturas con fecha en este periodo."
        />
        <BreakdownCard
          title="Principales proveedores"
          description="Según el monto USD de las autorizaciones."
          rows={data.providers.map((p) => ({
            key: p.provider,
            label: p.provider,
            value: p.usd > 0 ? p.usd : p.lines,
            display: p.usd > 0 ? formatUsdCompact(p.usd) : "—",
            hint: `${n(p.lines)} aut.`,
          }))}
          empty="Sin autorizaciones con fecha en este periodo."
        />
      </div>

      <div className="rise-in grid gap-6 lg:grid-cols-5" style={stagger(4)}>
        <SectionCard
          className="lg:col-span-3"
          title="Embudo de autorizaciones"
          description="Cuántas autorizaciones del periodo ya tienen factura vinculada."
        >
          <div className="space-y-6">
            <Meter label="Autorizaciones con factura" value={authorization.linked} total={authorization.lines} />
            <dl className="grid gap-4 sm:grid-cols-3">
              {[
                { label: "Solicitado", value: authorization.requestedUsd },
                { label: "Autorizado", value: authorization.authorized },
                { label: "Cobertura", value: authorization.coverage },
              ].map((item) => (
                <div key={item.label} className="rounded-2xl bg-muted px-4 py-3">
                  <dt className="text-xs text-muted-foreground">{item.label}</dt>
                  <dd className="mt-1 text-xl font-semibold tabular-nums text-foreground">
                    {formatUsdCompact(item.value)}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </SectionCard>

        <SectionCard className="lg:col-span-2" title="Canal de ingreso" description="Facturas por canal en el periodo.">
          <DonutChart
            centerLabel="facturas"
            keep={4}
            slices={data.byChannel.map((c) => ({ key: c.channel, label: c.channel, value: c.invoices }))}
          />
        </SectionCard>
      </div>

      <SectionCard
        className="rise-in"
        title="Composición documental"
        description="Todos los documentos del archivo, sin filtro de periodo."
      >
        <DonutChart
          centerLabel="documentos"
          keep={5}
          slices={data.documentMix.map((d) => ({
            key: d.key,
            label: DOCUMENT_TYPE_LABELS[d.key] || d.key,
            value: d.n,
          }))}
        />
      </SectionCard>

      {data.undated > 0 ? (
        <p className="text-center text-sm text-muted-foreground">
          {n(data.undated)} facturas no tienen fecha de emisión y no se incluyen en los totales por periodo.
        </p>
      ) : null}
    </div>
  );
}
