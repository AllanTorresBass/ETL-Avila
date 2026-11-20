import type { Metadata } from "next";
import Link from "next/link";
import { BadgeCheck, CircleDollarSign, Gauge, ReceiptText } from "lucide-react";
import { BreakdownList } from "@/components/breakdown-card";
import { DashboardHeader } from "@/components/dashboard-header";
import { DashboardNotice } from "@/components/dashboard-notice";
import { DashboardTabs } from "@/components/dashboard-tabs";
import { DonutChart } from "@/components/donut-chart";
import { KpiCard } from "@/components/kpi-card";
import { Meter } from "@/components/meter";
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

      <div className="rise-in" style={stagger(1)}>
        <DashboardTabs
          ariaLabel="Secciones del tablero de negocio"
          panels={[
            {
              id: "indicadores",
              label: "Indicadores",
              title: "Indicadores clave",
              description: `Resumen del periodo · ${rangeLabel.toLowerCase()}.`,
              body: (
                <div className="space-y-4">
                  {totals.invoices > 0 && totals.usdCoverage < 0.9 ? (
                    <p
                      role="status"
                      className="rounded-2xl border border-border bg-muted px-4 py-3 text-sm text-muted-foreground"
                    >
                      Solo {formatPercent(totals.usdCoverage)} de las facturas del periodo tiene monto en USD leído (
                      {n(totals.withUsd)} de {n(totals.invoices)}). Los totales de dinero reflejan únicamente esas
                      facturas.
                    </p>
                  ) : null}
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
                  </div>
                  {data.undated > 0 ? (
                    <p className="text-sm text-muted-foreground">
                      {n(data.undated)} facturas no tienen fecha de emisión y no se incluyen en los totales por periodo.
                    </p>
                  ) : null}
                </div>
              ),
            },
            {
              id: "evolucion",
              label: "Evolución",
              title: "Evolución mensual",
              description: "Monto facturado y número de facturas por mes de emisión.",
              body: <TrendChart data={data.monthly} />,
            },
            {
              id: "cuentas",
              label: "Cuentas",
              count: n(data.byAccount.length),
              title: "Cuentas y proveedores",
              description: "Principales cuentas por monto USD y proveedores por autorizaciones.",
              body: (
                <div className="grid gap-8 lg:grid-cols-2">
                  <div>
                    <h3 className="text-sm font-medium text-foreground">Principales cuentas</h3>
                    <p className="mb-3 text-xs text-muted-foreground">Ordenadas por monto facturado en USD.</p>
                    <BreakdownList
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
                  </div>
                  <div>
                    <h3 className="text-sm font-medium text-foreground">Principales proveedores</h3>
                    <p className="mb-3 text-xs text-muted-foreground">
                      Según el monto USD de las autorizaciones.
                    </p>
                    <BreakdownList
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
                </div>
              ),
            },
            {
              id: "autorizaciones",
              label: "Autorizaciones",
              count: n(authorization.lines),
              title: "Embudo de autorizaciones",
              description: "Cobertura de vínculo y canal de ingreso en el periodo.",
              body: (
                <div className="grid gap-6 lg:grid-cols-5">
                  <div className="space-y-6 lg:col-span-3">
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
                  <div className="lg:col-span-2">
                    <h3 className="mb-3 text-sm font-medium text-foreground">Canal de ingreso</h3>
                    <DonutChart
                      centerLabel="facturas"
                      keep={4}
                      slices={data.byChannel.map((c) => ({ key: c.channel, label: c.channel, value: c.invoices }))}
                    />
                  </div>
                </div>
              ),
            },
            {
              id: "documentos",
              label: "Documentos",
              count: n(data.documentMix.reduce((sum, d) => sum + d.n, 0)),
              title: "Composición documental",
              description: "Todos los documentos del archivo, sin filtro de periodo.",
              body: (
                <DonutChart
                  centerLabel="documentos"
                  keep={5}
                  slices={data.documentMix.map((d) => ({
                    key: d.key,
                    label: DOCUMENT_TYPE_LABELS[d.key] || d.key,
                    value: d.n,
                  }))}
                />
              ),
            },
          ]}
        />
      </div>

      <p className="text-center text-sm text-muted-foreground">
        ¿Quieres el resumen de calidad y negocio juntos?{" "}
        <Link href="/informe" className="font-medium text-brand underline-offset-4 hover:underline">
          Abre el informe
        </Link>
        .
      </p>
    </div>
  );
}
