import type { Metadata } from "next";
import Link from "next/link";
import { BadgeCheck, CircleDollarSign, Link2, ReceiptText } from "lucide-react";
import { AttentionPanel, type AttentionItem } from "@/components/attention-panel";
import { BreakdownCard, BreakdownList } from "@/components/breakdown-card";
import { DashboardHeader } from "@/components/dashboard-header";
import { DashboardNotice } from "@/components/dashboard-notice";
import { InformeExportBar, type InformeCsvTable } from "@/components/informe-export-bar";
import { KpiCard } from "@/components/kpi-card";
import { Meter } from "@/components/meter";
import { SectionCard } from "@/components/section-card";
import { TrendChart } from "@/components/trend-chart";
import { CONTACT_GAP_COPY } from "@/lib/contact-gap";
import { BI_RANGES, parseRange } from "@/lib/dashboard-data";
import { DOCUMENT_TYPE_LABELS } from "@/lib/db";
import { formatAccount } from "@/lib/format";
import { formatPercent, formatUsd, formatUsdCompact, percentChange } from "@/lib/format-metrics";
import { getInformeData } from "@/lib/informe-data";
import { REVIEW_KIND_LABELS } from "@/lib/review";

export const metadata: Metadata = {
  title: "Informe · Ávila GPS",
  description: "Resumen ejecutivo y de calidad del archivo: facturación, vínculos, contacto y cola de revisión.",
};

export const dynamic = "force-dynamic";

const n = (v: number) => v.toLocaleString("es-VE");
const stagger = (i: number) => ({ "--i": i }) as React.CSSProperties;

const FIELD_LABELS: Record<string, string> = {
  birth_date: "Nacimiento",
  phone: "Teléfono",
  address: "Dirección",
};

function RangeTabs({ current }: { current: string }) {
  return (
    <nav aria-label="Periodo" className="inline-flex flex-wrap gap-1 rounded-full border border-border bg-card p-1 shadow-sm">
      {BI_RANGES.map((r) => {
        const active = r.id === current;
        return (
          <Link
            key={r.id}
            href={`/informe?rango=${r.id}`}
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

export default async function InformePage({ searchParams }: PageProps<"/informe">) {
  const range = parseRange((await searchParams).rango);
  const data = await getInformeData(range);
  const rangeLabel = BI_RANGES.find((r) => r.id === range)?.label ?? "";
  const comparable = data.months > 0;
  const usdDelta = comparable ? percentChange(data.totals.usd, data.previous.usd) : null;
  const invoiceDelta = comparable ? percentChange(data.totals.invoices, data.previous.invoices) : null;

  const openByKind = new Map<string, number>();
  for (const r of data.reviews) {
    if (r.status === "open") openByKind.set(r.kind, (openByKind.get(r.kind) ?? 0) + r.n);
  }
  const reviewRows = [...openByKind.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([kind, count]) => ({
      key: kind,
      label: REVIEW_KIND_LABELS[kind] ?? kind,
      value: count,
      display: n(count),
      href: "/revision",
    }));

  const authMatchOpen = openByKind.get("auth_match") ?? 0;

  const attention: AttentionItem[] = [
    {
      id: "failed",
      title: "Documentos con carga fallida en Blob",
      hint: "Revisa la ruta de origen y vuelve a subirlos.",
      count: data.counts.failed,
      href: "/documentos?upload_status=failed",
      tone: "danger",
    },
    {
      id: "roles",
      title: "Casos de rol por resolver",
      hint: "Conflictos de cédula, titular del libro o varias cédulas.",
      count: data.kpi.openRoleReviews,
      href: "/revision",
      tone: "warning",
    },
    {
      id: "auth",
      title: "Autorizaciones sin factura vinculada",
      hint: "Líneas de sábana que aún no cruzan con una factura.",
      count: authMatchOpen,
      href: "/revision?tipo=autorizacion",
      tone: "warning",
    },
    {
      id: "no-titular",
      title: "Facturas sin titular",
      hint: "No se puede atribuir la factura a una persona.",
      count: data.roles.noTitular,
      href: "/facturas",
      tone: "info",
    },
    {
      id: "contact",
      title: "Personas con gaps de contacto",
      hint: "Nacimiento, teléfono o dirección sin dato usable.",
      count: data.contact.withAnyGap,
      href: "/personas",
      tone: "info",
    },
  ];

  const csvTables: InformeCsvTable[] = [
    {
      name: "mensual",
      headers: ["mes", "usd", "facturas"],
      rows: data.monthly.map((p) => [p.month, p.usd, p.invoices]),
    },
    {
      name: "cuentas",
      headers: ["codigo", "nombre", "usd", "facturas"],
      rows: data.byAccount.map((a) => [a.code ?? "", a.name, a.usd, a.invoices]),
    },
    {
      name: "canales",
      headers: ["canal", "usd", "facturas"],
      rows: data.byChannel.map((c) => [c.channel, c.usd, c.invoices]),
    },
    {
      name: "revision_abierta",
      headers: ["kind", "count"],
      rows: reviewRows.map((r) => [r.key, r.value]),
    },
    {
      name: "contact_gaps",
      headers: ["field", "code", "count"],
      rows: data.contact.byCode.map((g) => [g.field, g.code, g.n]),
    },
    {
      name: "documentos_archivo",
      headers: ["document_type", "count"],
      rows: data.documentMix.map((d) => [d.key, d.n]),
    },
  ];

  return (
    <div className="informe-page space-y-8">
      <div className="rise-in">
        <DashboardHeader
          current="informe"
          title="Informe del archivo"
          description="Un solo vistazo: cuánto se factura, qué tan bien se cruzan las fuentes y qué falta por decidir."
          actions={
            <div className="flex flex-col items-start gap-2 sm:items-end">
              <RangeTabs current={range} />
              <InformeExportBar rangeLabel={range} tables={csvTables} />
            </div>
          }
        />
      </div>

      <DashboardNotice failures={data.failures} />

      <section aria-label="Resumen ejecutivo" className="rise-in grid gap-4 sm:grid-cols-2 lg:grid-cols-4" style={stagger(1)}>
        <KpiCard
          featured
          label={`Facturado en USD · ${rangeLabel.toLowerCase()}`}
          value={formatUsdCompact(data.totals.usd)}
          hint={data.totals.usd > 0 ? formatUsd(data.totals.usd) : "Sin montos en el periodo"}
          delta={usdDelta}
          deltaLabel="frente al periodo anterior"
          href="/bi"
          icon={<CircleDollarSign className="size-4" />}
        />
        <KpiCard
          label="Facturas del periodo"
          value={n(data.totals.invoices)}
          delta={invoiceDelta}
          hint={comparable ? "vs. periodo anterior" : undefined}
          href="/facturas"
          icon={<ReceiptText className="size-4" />}
        />
        <KpiCard
          label="Cola de revisión abierta"
          value={n(data.kpi.openReviews)}
          hint={`${n(data.kpi.openRoleReviews)} de rol`}
          href="/revision"
          icon={<BadgeCheck className="size-4" />}
        />
        <KpiCard
          label="Autorizaciones con factura"
          value={data.authLinkage.lines > 0 ? formatPercent(data.authLinkage.ratio) : "—"}
          hint={`${n(data.authLinkage.linked)} de ${n(data.authLinkage.lines)}`}
          href="/etl"
          icon={<Link2 className="size-4" />}
        />
      </section>

      <section
        aria-label="Confianza de los datos"
        className="rise-in rounded-3xl border border-border bg-muted/60 px-5 py-4"
        style={stagger(2)}
      >
        <h2 className="text-sm font-semibold text-foreground">Confianza de los datos</h2>
        <ul className="mt-2 space-y-1.5 text-sm text-muted-foreground">
          <li>
            Solo {formatPercent(data.totals.usdCoverage)} de las facturas con fecha en el periodo tiene monto USD leído (
            {n(data.totals.withUsd)} de {n(data.totals.invoices)}). Los totales de dinero usan únicamente esas facturas.
          </li>
          <li>
            {n(data.undated)} facturas no tienen fecha de emisión y quedan fuera de los totales por periodo.
          </li>
          <li>
            La composición documental más abajo describe todo el archivo, no solo el periodo seleccionado.
          </li>
        </ul>
      </section>

      <SectionCard
        className="rise-in"
        title="Evolución mensual"
        description={`Monto facturado y número de facturas por mes de emisión · ${rangeLabel.toLowerCase()}.`}
      >
        <TrendChart data={data.monthly} />
      </SectionCard>

      <div className="rise-in grid gap-6 lg:grid-cols-2" style={stagger(3)}>
        <BreakdownCard
          title="Principales cuentas"
          description="Ordenadas por monto facturado en USD en el periodo."
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
          title="Canales de ingreso"
          description="Facturas del periodo agrupadas por canal."
          rows={data.byChannel.map((c) => ({
            key: c.channel,
            label: c.channel,
            value: c.invoices,
            display: n(c.invoices),
            hint: c.usd > 0 ? formatUsdCompact(c.usd) : undefined,
          }))}
          empty="Sin facturas con fecha en este periodo."
        />
      </div>

      <div className="rise-in grid gap-6 lg:grid-cols-5" style={stagger(4)}>
        <SectionCard
          className="lg:col-span-3"
          title="Calidad del vínculo"
          description="Qué tan completo está el cruce entre personas, facturas y autorizaciones."
        >
          <div className="grid gap-6 md:grid-cols-2">
            <Meter
              label="Facturas con titular"
              value={data.roles.withTitular}
              total={data.roles.invoices}
              href="/facturas"
            />
            <Meter
              label="Facturas con titular y beneficiario"
              value={data.roles.titularAndBeneficiario}
              total={data.roles.invoices}
            />
            <Meter
              label="Autorizaciones con factura"
              value={data.authLinkage.linked}
              total={data.authLinkage.lines}
              href="/revision?tipo=autorizacion"
            />
            <Meter
              label="Documentos subidos a Blob"
              value={data.counts.uploaded}
              total={data.counts.documents}
              href="/documentos?upload_status=failed"
            />
          </div>
        </SectionCard>

        <SectionCard
          className="lg:col-span-2"
          title="Completitud de contacto"
          description="Personas con gaps registrados por el enriquecimiento."
        >
          {data.contact.withAnyGap === 0 && data.contact.byCode.length === 0 ? (
            <p className="text-sm text-muted-foreground">Sin gaps de contacto registrados.</p>
          ) : (
            <div className="space-y-5">
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-2xl bg-muted px-3 py-2">
                  <dt className="text-xs text-muted-foreground">Con cédula</dt>
                  <dd className="mt-0.5 text-lg font-semibold tabular-nums">{n(data.contact.withCi)}</dd>
                </div>
                <div className="rounded-2xl bg-muted px-3 py-2">
                  <dt className="text-xs text-muted-foreground">Sin cédula</dt>
                  <dd className="mt-0.5 text-lg font-semibold tabular-nums">{n(data.contact.withoutCi)}</dd>
                </div>
                <div className="rounded-2xl bg-muted px-3 py-2">
                  <dt className="text-xs text-muted-foreground">Gaps nacimiento</dt>
                  <dd className="mt-0.5 text-lg font-semibold tabular-nums">{n(data.contact.birthDateGaps)}</dd>
                </div>
                <div className="rounded-2xl bg-muted px-3 py-2">
                  <dt className="text-xs text-muted-foreground">Gaps teléfono</dt>
                  <dd className="mt-0.5 text-lg font-semibold tabular-nums">{n(data.contact.phoneGaps)}</dd>
                </div>
              </dl>
              <BreakdownList
                rows={data.contact.byCode.map((g) => ({
                  key: `${g.field}-${g.code}`,
                  label: `${FIELD_LABELS[g.field] ?? g.field}: ${CONTACT_GAP_COPY[g.code] ?? g.code}`,
                  value: g.n,
                  display: n(g.n),
                }))}
                empty="Sin gaps de contacto registrados."
              />
            </div>
          )}
        </SectionCard>
      </div>

      <div className="rise-in grid gap-6 lg:grid-cols-2" style={stagger(5)}>
        <BreakdownCard
          title="Cola de revisión abierta"
          description="Casos que necesitan una decisión humana, por tipo."
          rows={reviewRows}
          empty="No hay casos abiertos. La cola está al día."
        />
        <BreakdownCard
          title="Documentos del archivo"
          description="Inventario clasificado · todo el archivo, sin filtro de periodo."
          rows={data.documentMix.map((row) => ({
            key: row.key,
            label: DOCUMENT_TYPE_LABELS[row.key] || row.key,
            value: row.n,
            display: n(row.n),
            href: `/documentos?type=${row.key}`,
          }))}
          empty="Aún no hay documentos cargados."
        />
      </div>

      <div className="rise-in" style={stagger(6)}>
        <AttentionPanel items={attention} />
      </div>

      <footer className="rise-in space-y-3 border-t border-border pt-6 text-sm text-muted-foreground" style={stagger(7)}>
        <h2 className="text-sm font-semibold text-foreground">Cómo leer este informe</h2>
        <ul className="list-disc space-y-1.5 pl-5">
          <li>
            <span className="font-medium text-foreground">Facturado en USD</span> suma solo facturas con fecha de
            emisión en el periodo y con monto USD leído.
          </li>
          <li>
            <span className="font-medium text-foreground">Autorizaciones con factura</span> mide líneas de sábana ya
            vinculadas a una factura, no el embudo de montos autorizados.
          </li>
          <li>
            <span className="font-medium text-foreground">Gaps de contacto</span> vienen del enriquecimiento de personas
            (códigos de nacimiento, teléfono y dirección); el CSV solo exporta conteos.
          </li>
          <li>
            Periodo activo: <span className="font-medium text-foreground">{rangeLabel}</span>. Generado al cargar la
            página.
          </li>
        </ul>
        <p className="text-center">
          ¿Quieres el detalle operativo o el de negocio?{" "}
          <Link href="/etl" className="font-medium text-brand underline-offset-4 hover:underline">
            ETL
          </Link>
          {" · "}
          <Link href="/bi" className="font-medium text-brand underline-offset-4 hover:underline">
            Negocio
          </Link>
        </p>
      </footer>
    </div>
  );
}
