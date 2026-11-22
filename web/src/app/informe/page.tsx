import type { Metadata } from "next";
import Link from "next/link";
import { BadgeCheck, CircleDollarSign, FlaskConical, Link2, ReceiptText, Stethoscope } from "lucide-react";
import { AttentionPanel, type AttentionItem } from "@/components/attention-panel";
import { BreakdownList } from "@/components/breakdown-card";
import { DashboardHeader } from "@/components/dashboard-header";
import { DashboardNotice } from "@/components/dashboard-notice";
import { DashboardTabs } from "@/components/dashboard-tabs";
import { EntityRow } from "@/components/entity-row";
import { InformeExportBar, type InformeCsvTable } from "@/components/informe-export-bar";
import { KpiCard } from "@/components/kpi-card";
import { Meter } from "@/components/meter";
import { TrendChart } from "@/components/trend-chart";
import { CONTACT_GAP_COPY } from "@/lib/contact-gap";
import { BI_RANGES, parseRange } from "@/lib/dashboard-data";
import { DOCUMENT_TYPE_LABELS } from "@/lib/db";
import { formatAccount, formatDate, formatInvoiceNumber } from "@/lib/format";
import { formatPercent, formatUsd, formatUsdCompact, percentChange } from "@/lib/format-metrics";
import { getInformeData } from "@/lib/informe-data";
import { LINK_STATUS_LABELS } from "@/lib/medico-data";
import { REVIEW_GROUPS, REVIEW_KIND_LABELS } from "@/lib/review";

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

function reviewHref(kind: string): string {
  const group = REVIEW_GROUPS.find((g) => g.kinds.includes(kind));
  return group ? `/revision?tipo=${group.id}` : "/revision";
}

function ListFooter({ href, label }: { href: string; label: string }) {
  return (
    <p className="mt-4 text-center text-sm">
      <Link href={href} className="font-medium text-brand underline-offset-4 hover:underline">
        {label}
      </Link>
    </p>
  );
}

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
      href: reviewHref(kind),
    }));

  const authMatchOpen = openByKind.get("auth_match") ?? 0;
  const attentionCount = [
    data.counts.failed,
    data.kpi.openRoleReviews,
    authMatchOpen,
    data.roles.noTitular,
    data.contact.withAnyGap,
  ].reduce((sum, c) => sum + c, 0);

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
      title: "Personas con contacto incompleto",
      hint: "Nacimiento, teléfono o dirección sin dato usable.",
      count: data.contact.withAnyGap,
      href: "/personas",
      tone: "info",
    },
  ];

  const personasCsv: InformeCsvTable[] = [
    {
      name: "personas",
      headers: ["id", "nombre", "ci", "facturas", "usd"],
      rows: data.lists.topClients.map((c) => [c.id, c.name, c.identityNumber ?? "", c.invoices, c.usd]),
    },
  ];

  const facturasCsv: InformeCsvTable[] = [
    {
      name: "facturas",
      headers: ["id", "factura", "cuenta", "usd", "fecha"],
      rows: data.lists.topInvoices.map((i) => [
        i.id,
        i.invoiceNumber,
        i.account ?? "",
        i.usd ?? "",
        i.issueDate ?? "",
      ]),
    },
  ];

  return (
    <div className="informe-page space-y-8">
      <div className="rise-in">
        <DashboardHeader
          current="informe"
          title="Informe del archivo"
          description="Un solo vistazo: cuánto se factura, qué tan bien se cruzan las fuentes y qué falta por decidir."
          actions={<RangeTabs current={range} />}
        />
      </div>

      <DashboardNotice failures={data.failures} />

      <div className="rise-in" style={stagger(1)}>
        <DashboardTabs
          ariaLabel="Secciones del informe"
          panels={[
            {
              id: "resumen",
              label: "Resumen",
              title: "Resumen ejecutivo",
              description: `Indicadores del periodo · ${rangeLabel.toLowerCase()}.`,
              body: (
                <div className="space-y-5">
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
                      href="/autorizaciones?vista=analisis"
                      icon={<Link2 className="size-4" />}
                    />
                  </div>
                  <div className="rounded-2xl border border-border bg-muted/60 px-4 py-3">
                    <h3 className="text-sm font-semibold text-foreground">Confianza de los datos</h3>
                    <ul className="mt-2 space-y-1.5 text-sm text-muted-foreground">
                      <li>
                        Solo {formatPercent(data.totals.usdCoverage)} de las facturas con fecha en el periodo tiene
                        monto USD leído ({n(data.totals.withUsd)} de {n(data.totals.invoices)}). Los totales de dinero
                        usan únicamente esas facturas.
                      </li>
                      <li>
                        {n(data.undated)} facturas no tienen fecha de emisión y quedan fuera de los totales por
                        periodo.
                      </li>
                      <li>
                        La pestaña Documentos describe todo el archivo, no solo el periodo seleccionado.
                      </li>
                    </ul>
                  </div>
                </div>
              ),
            },
            {
              id: "evolucion",
              label: "Evolución",
              title: "Evolución mensual",
              description: `Monto facturado y número de facturas por mes de emisión · ${rangeLabel.toLowerCase()}.`,
              body: <TrendChart data={data.monthly} />,
            },
            {
              id: "negocio",
              label: "Negocio",
              count: n(data.byAccount.length),
              title: "Cuentas y canales",
              description: "Principales cuentas y canales de ingreso en el periodo.",
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
                    <h3 className="text-sm font-medium text-foreground">Canales de ingreso</h3>
                    <p className="mb-3 text-xs text-muted-foreground">Facturas del periodo agrupadas por canal.</p>
                    <BreakdownList
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
                </div>
              ),
            },
            {
              id: "calidad",
              label: "Calidad",
              title: "Calidad del vínculo y contacto",
              description: "Cruce entre personas, facturas y autorizaciones, más el contacto incompleto.",
              body: (
                <div className="grid gap-8 lg:grid-cols-5">
                  <div className="grid gap-6 md:grid-cols-2 lg:col-span-3">
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
                      label="Paciente distinto sin beneficiario"
                      value={data.roles.mismatchNoBeneficiario}
                      total={data.roles.invoices}
                      href="/facturas?role_gap=mismatch"
                    />
                    <Meter
                      label="ID sin cédula en titular"
                      value={data.roles.idDocsNoCi}
                      total={data.roles.invoices}
                      href="/facturas?role_gap=no_ci"
                    />
                    <Meter
                      label="Autorizaciones con factura"
                      value={data.authLinkage.linked}
                      total={data.authLinkage.lines}
                      href="/autorizaciones?estado=pendiente#lista"
                    />
                    <Meter
                      label="Documentos subidos a Blob"
                      value={data.counts.uploaded}
                      total={data.counts.documents}
                      href="/documentos?upload_status=failed"
                    />
                  </div>
                  <div className="lg:col-span-2">
                    <h3 className="mb-3 text-sm font-medium text-foreground">Completitud de contacto</h3>
                    {data.contact.withAnyGap === 0 && data.contact.byCode.length === 0 ? (
                      <p className="text-sm text-muted-foreground">No hay contacto incompleto.</p>
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
                            <dt className="text-xs text-muted-foreground">Nacimiento incompleto</dt>
                            <dd className="mt-0.5 text-lg font-semibold tabular-nums">
                              {n(data.contact.birthDateGaps)}
                            </dd>
                          </div>
                          <div className="rounded-2xl bg-muted px-3 py-2">
                            <dt className="text-xs text-muted-foreground">Teléfono incompleto</dt>
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
                          empty="No hay contacto incompleto."
                        />
                      </div>
                    )}
                  </div>
                </div>
              ),
            },
            {
              id: "atencion",
              label: "Atención",
              count: n(attentionCount),
              title: "Qué necesita atención",
              description: "Cola de revisión, documentos fallidos y pendientes operativos.",
              body: (
                <div className="space-y-8">
                  <AttentionPanel items={attention} embedded />
                  <div className="grid gap-8 lg:grid-cols-2">
                    <div>
                      <h3 className="text-sm font-medium text-foreground">Cola de revisión abierta</h3>
                      <p className="mb-3 text-xs text-muted-foreground">Casos por tipo.</p>
                      <BreakdownList
                        rows={reviewRows}
                        empty="No hay casos abiertos. La cola está al día."
                      />
                    </div>
                    <div>
                      <h3 className="text-sm font-medium text-foreground">Documentos del archivo</h3>
                      <p className="mb-3 text-xs text-muted-foreground">Inventario clasificado · todo el archivo.</p>
                      <BreakdownList
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
                  </div>
                </div>
              ),
            },
            {
              id: "clinico",
              label: "Clínico",
              count: n(data.clinical.kpis.atenciones),
              title: "Médicos, especialidades y atenciones",
              description: "Leído de informes, órdenes, laboratorios e imágenes · todo el archivo.",
              body: (
                <div className="space-y-6">
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    <KpiCard
                      label="Médicos"
                      value={n(data.clinical.kpis.medicos)}
                      hint={`${n(data.clinical.kpis.conMpps)} con MPPS`}
                      href="/medicos"
                      icon={<Stethoscope className="size-4" />}
                    />
                    <KpiCard
                      label="Con especialidad"
                      value={n(data.clinical.kpis.conEspecialidad)}
                      hint={
                        data.clinical.kpis.medicos > 0
                          ? formatPercent(data.clinical.kpis.conEspecialidad / data.clinical.kpis.medicos)
                          : undefined
                      }
                      href="/especialidades"
                    />
                    <KpiCard
                      label="Atenciones"
                      value={n(data.clinical.kpis.atenciones)}
                      hint={`${n(data.clinical.kpis.completas)} con paciente, médico y especialidad`}
                    />
                    <KpiCard
                      label="Casos clínicos abiertos"
                      value={n(data.clinical.kpis.openReviews)}
                      href="/revision?tipo=medico"
                    />
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    <KpiCard
                      label="Facturas con un estudio"
                      value={n(data.estudios.facturas)}
                      href="/estudios"
                      icon={<FlaskConical className="size-4" />}
                    />
                    <KpiCard label="Con cargo del estudio" value={n(data.estudios.charged)} href="/estudios" />
                    <KpiCard label="Con hoja de resultado" value={n(data.estudios.withResult)} href="/estudios" />
                    <KpiCard
                      label="Cobradas sin resultado"
                      value={n(data.estudios.chargedWithoutResult)}
                      href="/estudios"
                    />
                  </div>
                  <div>
                    <h3 className="text-sm font-medium text-foreground">Estudios por tipo</h3>
                    <p className="mb-3 text-xs text-muted-foreground">Facturas con el cargo, la hoja o la orden. La consulta no entra.</p>
                    <BreakdownList
                      rows={data.estudios.families.map((row) => ({
                        key: row.id,
                        label: row.label,
                        value: row.n,
                        display: n(row.n),
                        href: `/estudios?familia=${row.id}`,
                      }))}
                      empty="Aún no hay estudios cargados."
                    />
                  </div>
                  <div className="grid gap-8 lg:grid-cols-2">
                    <div>
                      <h3 className="text-sm font-medium text-foreground">Especialidades con más atenciones</h3>
                      <p className="mb-3 text-xs text-muted-foreground">Incluye sus subespecialidades.</p>
                      <BreakdownList
                        rows={data.clinical.topEspecialidades.map((row) => ({
                          key: row.code,
                          label: row.name_es,
                          value: row.atenciones,
                          display: n(row.atenciones),
                          hint: `${row.area_name} · ${n(row.medicos)} médicos`,
                          href: `/medicos?especialidad=${row.code}`,
                        }))}
                        empty="Aún no hay atenciones cargadas."
                      />
                    </div>
                    <div>
                      <h3 className="text-sm font-medium text-foreground">Estado del vínculo</h3>
                      <p className="mb-3 text-xs text-muted-foreground">Paciente, médico y especialidad por atención.</p>
                      <BreakdownList
                        rows={data.clinical.statuses.map((row) => ({
                          key: row.status,
                          label: LINK_STATUS_LABELS[row.status] || row.status,
                          value: row.n,
                          display: n(row.n),
                        }))}
                        empty="Aún no hay atenciones cargadas."
                      />
                    </div>
                  </div>
                </div>
              ),
            },
            {
              id: "clientes",
              label: "Clientes",
              count: n(data.lists.topClients.length),
              title: "Principales clientes (titulares)",
              description: `Titulares con más monto USD en facturas del periodo · ${rangeLabel.toLowerCase()}.`,
              body: (
                <div className="space-y-4">
                  <InformeExportBar section="personas" rangeLabel={range} tables={personasCsv} />
                  {data.lists.topClients.length === 0 ? (
                    <p className="text-sm text-muted-foreground">Sin titulares con facturas fechadas en este periodo.</p>
                  ) : (
                    <ul className="space-y-2">
                      {data.lists.topClients.map((c) => (
                        <li key={c.id}>
                          <EntityRow
                            href={`/personas/${c.id}?tab=facturas`}
                            title={c.name}
                            meta={c.identityNumber ? `Cédula ${c.identityNumber}` : "Sin cédula"}
                            badges={[`${n(c.invoices)} fact.`]}
                            trailing={c.usd > 0 ? formatUsdCompact(c.usd) : undefined}
                          />
                        </li>
                      ))}
                    </ul>
                  )}
                  <ListFooter href="/personas?role=titular" label="Ver todos los clientes" />
                </div>
              ),
            },
            {
              id: "facturas",
              label: "Facturas",
              count: n(data.lists.topInvoices.length),
              title: "Facturas de mayor monto",
              description: `Facturas con monto USD leído en el periodo · ${rangeLabel.toLowerCase()}.`,
              body: (
                <div className="space-y-4">
                  <InformeExportBar section="facturas" rangeLabel={range} tables={facturasCsv} />
                  {data.lists.topInvoices.length === 0 ? (
                    <p className="text-sm text-muted-foreground">Sin facturas con monto USD en este periodo.</p>
                  ) : (
                    <ul className="space-y-2">
                      {data.lists.topInvoices.map((inv) => (
                        <li key={inv.id}>
                          <EntityRow
                            href={`/facturas/${inv.id}`}
                            title={formatInvoiceNumber(inv.invoiceNumber)}
                            meta={[formatAccount(inv.account), formatDate(inv.issueDate)].filter(Boolean).join(" · ")}
                            trailing={inv.usd != null ? formatUsdCompact(inv.usd) : undefined}
                          />
                        </li>
                      ))}
                    </ul>
                  )}
                  <ListFooter href="/facturas" label="Ver todas las facturas" />
                </div>
              ),
            },
            {
              id: "sin-titular",
              label: "Sin titular",
              count: n(data.roles.noTitular),
              title: "Facturas sin titular",
              description: "Muestra de facturas que aún no tienen una persona en rol titular.",
              body: (
                <>
                  {data.lists.invoicesNoTitular.length === 0 ? (
                    <p className="text-sm text-muted-foreground">Todas las facturas tienen titular.</p>
                  ) : (
                    <ul className="space-y-2">
                      {data.lists.invoicesNoTitular.map((inv) => (
                        <li key={inv.id}>
                          <EntityRow
                            href={`/facturas/${inv.id}`}
                            title={formatInvoiceNumber(inv.invoiceNumber)}
                            meta={[formatAccount(inv.account), formatDate(inv.issueDate)].filter(Boolean).join(" · ")}
                            badges={["Sin titular"]}
                          />
                        </li>
                      ))}
                    </ul>
                  )}
                  <ListFooter href="/facturas?has_person=0" label="Abrir facturas sin persona vinculada" />
                </>
              ),
            },
            {
              id: "sin-ci",
              label: "Sin cédula",
              count: n(data.contact.withoutCi),
              title: "Clientes sin cédula",
              description: "Personas del archivo sin número de identidad, ordenadas por facturas vinculadas.",
              body: (
                <>
                  {data.lists.clientsNoCi.length === 0 ? (
                    <p className="text-sm text-muted-foreground">Todas las personas tienen cédula registrada.</p>
                  ) : (
                    <ul className="space-y-2">
                      {data.lists.clientsNoCi.map((c) => (
                        <li key={c.id}>
                          <EntityRow
                            href={`/personas/${c.id}`}
                            title={c.name}
                            meta="Sin cédula"
                            badges={c.invoices > 0 ? [`${n(c.invoices)} fact.`] : ["Sin facturas"]}
                          />
                        </li>
                      ))}
                    </ul>
                  )}
                  <ListFooter href="/personas?has_ci=0" label="Ver personas sin cédula" />
                </>
              ),
            },
            {
              id: "fallidos",
              label: "Fallidos",
              count: n(data.counts.failed),
              title: "Documentos con carga fallida",
              description: "Últimas páginas que no se subieron a Blob.",
              body: (
                <>
                  {data.lists.failedDocuments.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No hay documentos fallidos.</p>
                  ) : (
                    <ul className="space-y-2">
                      {data.lists.failedDocuments.map((d) => (
                        <li key={d.id}>
                          <EntityRow
                            href={`/documentos/${d.id}`}
                            title={DOCUMENT_TYPE_LABELS[d.documentType] || d.documentType}
                            meta={[
                              d.invoiceNumber ? formatInvoiceNumber(d.invoiceNumber) : null,
                              d.pageIndex != null ? `Página ${d.pageIndex}` : null,
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                            badges={["Fallido"]}
                          />
                        </li>
                      ))}
                    </ul>
                  )}
                  <ListFooter href="/documentos?upload_status=failed" label="Ver documentos fallidos" />
                </>
              ),
            },
            {
              id: "revision",
              label: "Revisión",
              count: n(data.kpi.openReviews),
              title: "Casos abiertos recientes",
              description: "Muestra de la cola de revisión, priorizada por puntuación.",
              body: (
                <>
                  {data.lists.openReviews.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No hay casos abiertos.</p>
                  ) : (
                    <ul className="space-y-2">
                      {data.lists.openReviews.map((r) => (
                        <li key={r.id}>
                          <EntityRow
                            href={reviewHref(r.kind)}
                            title={REVIEW_KIND_LABELS[r.kind] ?? r.kind}
                            meta={[
                              r.personName,
                              r.identityNumber ? `CI ${r.identityNumber}` : null,
                              r.invoiceNumber ? formatInvoiceNumber(r.invoiceNumber) : null,
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                          />
                        </li>
                      ))}
                    </ul>
                  )}
                  <ListFooter href="/revision" label="Abrir la cola de revisión" />
                </>
              ),
            },
          ]}
        />
      </div>

      <footer className="rise-in space-y-3 border-t border-border pt-6 text-sm text-muted-foreground" style={stagger(2)}>
        <h2 className="text-sm font-semibold text-foreground">Cómo leer este informe</h2>
        <ul className="list-disc space-y-1.5 pl-5">
          <li>
            <span className="font-medium text-foreground">Facturado en USD</span> suma solo facturas con fecha de
            emisión en el periodo y con monto USD leído.
          </li>
          <li>
            <span className="font-medium text-foreground">Listas</span> muestran hasta 10 filas de muestra; usa Ver todos
            para el inventario completo. Imprimir y CSV están solo en Clientes y Facturas.
          </li>
          <li>
            <span className="font-medium text-foreground">Autorizaciones con factura</span> mide líneas de sábana ya
            vinculadas a una factura, no el embudo de montos autorizados.
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
