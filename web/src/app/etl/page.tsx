import type { Metadata } from "next";
import Link from "next/link";
import { Files, FileText, ReceiptText, Users } from "lucide-react";
import { AttentionPanel, type AttentionItem } from "@/components/attention-panel";
import { BreakdownList } from "@/components/breakdown-card";
import { DashboardHeader } from "@/components/dashboard-header";
import { EtlDetailTabs } from "@/components/etl-detail-tabs";
import { DashboardNotice } from "@/components/dashboard-notice";
import { KpiCard } from "@/components/kpi-card";
import { Meter } from "@/components/meter";
import { SectionCard } from "@/components/section-card";
import { StatusStack, type StatusSegment } from "@/components/status-stack";
import { getEtlData } from "@/lib/dashboard-data";
import { DOCUMENT_TYPE_LABELS, UPLOAD_STATUS_LABELS } from "@/lib/db";
import { formatDateTime, formatDuration } from "@/lib/format-metrics";
import { REVIEW_KIND_LABELS, SOURCE_KIND_LABELS } from "@/lib/review";

export const metadata: Metadata = {
  title: "Tablero ETL · Ávila GPS",
  description: "Estado operativo del pipeline: cargas, calidad del vínculo y cola de revisión.",
};

export const dynamic = "force-dynamic";

const UPLOAD_TONE: Record<string, string> = {
  uploaded: "bg-success",
  pending: "bg-info",
  failed: "bg-danger",
  skipped: "bg-muted-foreground",
};

const n = (v: number) => v.toLocaleString("es-VE");
const stagger = (i: number) => ({ "--i": i }) as React.CSSProperties;

type EtlRun = Awaited<ReturnType<typeof getEtlData>>["runs"][number];

function RecentRuns({ runs }: { runs: EtlRun[] }) {
  if (runs.length === 0) {
    return <p className="text-sm text-muted-foreground">Aún no se ha registrado ninguna ejecución.</p>;
  }

  return (
    <div className="-mx-2 overflow-x-auto">
      <table className="w-full min-w-[34rem] text-left text-sm">
        <caption className="sr-only">Últimas ejecuciones del ETL</caption>
        <thead>
          <tr className="text-xs tracking-wide text-muted-foreground uppercase">
            <th scope="col" className="px-2 py-2 font-medium">Script</th>
            <th scope="col" className="px-2 py-2 font-medium">Modo</th>
            <th scope="col" className="px-2 py-2 font-medium">Inicio</th>
            <th scope="col" className="px-2 py-2 font-medium">Duración</th>
            <th scope="col" className="px-2 py-2 font-medium">Resultado</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {runs.map((run) => {
            const counters = Object.entries(run.counters)
              .filter(([, v]) => typeof v === "number")
              .slice(0, 3);
            return (
              <tr key={run.id}>
                <th scope="row" className="px-2 py-3 font-medium text-foreground">{run.script}</th>
                <td className="px-2 py-3">
                  <span
                    className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      run.mode === "apply" ? "bg-success-soft text-success" : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {run.mode === "apply" ? "Aplicada" : "Prueba"}
                  </span>
                </td>
                <td className="px-2 py-3 whitespace-nowrap text-muted-foreground">{formatDateTime(run.startedAt)}</td>
                <td className="px-2 py-3 whitespace-nowrap tabular-nums text-muted-foreground">
                  {formatDuration(run.startedAt, run.finishedAt)}
                </td>
                <td className="px-2 py-3 text-muted-foreground">
                  {counters.length === 0
                    ? "—"
                    : counters.map(([k, v]) => `${k.replace(/_/g, " ")}: ${n(v as number)}`).join(" · ")}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default async function EtlDashboardPage() {
  const data = await getEtlData();
  const { counts, kpi } = data;
  const latestRun = data.runs[0];

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
      count: kpi.openRoleReviews,
      href: "/revision",
      tone: "warning",
    },
    {
      id: "reviews",
      title: "Casos abiertos en la cola de revisión",
      hint: "Incluye todos los tipos, no solo los de rol.",
      count: kpi.openReviews,
      href: "/revision",
      tone: "warning",
    },
    {
      id: "no-titular",
      title: "Facturas sin titular",
      hint: "No se puede atribuir la factura a una persona.",
      count: kpi.invoicesNoTitular,
      href: "/facturas",
      tone: "info",
    },
    {
      id: "no-invoice",
      title: "Personas sin facturas",
      hint: "Clientes registrados que aún no tienen documentos.",
      count: kpi.personsNoInvoice,
      href: "/personas",
      tone: "info",
    },
  ];

  const uploadSegments: StatusSegment[] = ["uploaded", "pending", "failed", "skipped"].map((status) => ({
    key: status,
    label: UPLOAD_STATUS_LABELS[status] ?? status,
    value: data.uploads.find((u) => u.status === status)?.n ?? 0,
    tone: UPLOAD_TONE[status],
    href: `/documentos?upload_status=${status}`,
  }));

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

  const resolved = data.reviews.filter((r) => r.status !== "open").reduce((sum, r) => sum + r.n, 0);
  const totalReviews = resolved + kpi.openReviews;

  return (
    <div className="space-y-8">
      <div className="rise-in">
        <DashboardHeader
          current="etl"
          title="Operación del pipeline"
          description="Qué se cargó, qué tan bien se cruzaron las fuentes y qué necesita una decisión humana."
          actions={
            latestRun ? (
              <p className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground">
                <span
                  aria-hidden="true"
                  className={`size-2 rounded-full ${latestRun.finishedAt ? "bg-success" : "bg-warning"}`}
                />
                Última ejecución: <span className="font-medium text-foreground">{latestRun.script}</span> ·{" "}
                {formatDateTime(latestRun.startedAt)}
              </p>
            ) : null
          }
        />
      </div>

      <DashboardNotice failures={data.failures} />

      <div className="rise-in" style={stagger(1)}>
        <AttentionPanel items={attention} />
      </div>

      <section
        aria-label="Inventario"
        className="rise-in grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
        style={stagger(2)}
      >
        <KpiCard label="Personas" value={n(counts.persons)} href="/personas" icon={<Users className="size-4" />} />
        <KpiCard label="Facturas" value={n(counts.invoices)} href="/facturas" icon={<ReceiptText className="size-4" />} />
        <KpiCard label="Documentos" value={n(counts.documents)} href="/documentos" icon={<FileText className="size-4" />} />
        <KpiCard
          label="Archivos fuente"
          value={n(counts.sourceFiles)}
          hint={`${n(kpi.scanFiles)} de escáner`}
          icon={<Files className="size-4" />}
        />
      </section>

      <div className="rise-in grid gap-6 lg:grid-cols-5" style={stagger(3)}>
        <SectionCard
          className="lg:col-span-3"
          title="Calidad del vínculo"
          description="Qué tan completo está el cruce entre fuentes."
        >
          <div className="grid gap-6 md:grid-cols-2">
            <Meter label="Autorizaciones con factura" value={kpi.authLinked} total={kpi.authLines} />
            <Meter label="Facturas con titular por cédula" value={kpi.invoicesCiTitular} total={counts.invoices} />
            <Meter label="Facturas con beneficiario" value={kpi.invoicesWithBeneficiario} total={counts.invoices} />
            <Meter
              label="Documentos subidos a Blob"
              value={counts.uploaded}
              total={counts.documents}
              href="/documentos?upload_status=failed"
            />
          </div>
        </SectionCard>

        <SectionCard
          className="lg:col-span-2"
          title="Estado de carga a Blob"
          description="Distribución de los documentos por resultado."
        >
          <StatusStack segments={uploadSegments} empty="Aún no hay documentos cargados." />
        </SectionCard>
      </div>

      <div className="rise-in" style={stagger(4)}>
        <EtlDetailTabs
          panels={[
            {
              id: "revision",
              label: "Revisión",
              count: n(kpi.openReviews),
              title: "Cola de revisión abierta",
              description:
                totalReviews > 0
                  ? `${n(resolved)} de ${n(totalReviews)} casos ya resueltos.`
                  : "Casos que necesitan una decisión humana.",
              body: <BreakdownList rows={reviewRows} empty="No hay casos abiertos. La cola está al día." />,
            },
            {
              id: "provenance",
              label: "Procedencia",
              count: n(data.provenance.reduce((sum, p) => sum + p.n, 0)),
              title: "Procedencia de los datos",
              description: "Origen de los campos escritos por el ETL y su confianza media.",
              body: (
                <BreakdownList
                  rows={data.provenance.map((p) => ({
                    key: p.sourceKind,
                    label: SOURCE_KIND_LABELS[p.sourceKind] ?? p.sourceKind,
                    value: p.n,
                    display: n(p.n),
                    hint: p.avgConfidence != null ? `${Math.round(p.avgConfidence * 100)}% conf.` : undefined,
                  }))}
                  empty="Aún no hay campos con procedencia registrada."
                />
              ),
            },
            {
              id: "runs",
              label: "Ejecuciones",
              count: n(data.runs.length),
              title: "Ejecuciones recientes",
              description: "Últimas corridas del ETL, en modo prueba o aplicadas.",
              body: <RecentRuns runs={data.runs} />,
            },
            {
              id: "documents",
              label: "Documentos",
              count: n(counts.documents),
              title: "Documentos por tipo",
              description: "Inventario clasificado por el ETL.",
              body: (
                <BreakdownList
                  rows={data.byType.map((row) => ({
                    key: row.key,
                    label: DOCUMENT_TYPE_LABELS[row.key] || row.key,
                    value: row.n,
                    display: n(row.n),
                    href: `/documentos?type=${row.key}`,
                  }))}
                  empty="Aún no hay documentos cargados."
                />
              ),
            },
          ]}
        />
      </div>

      <p className="text-center text-sm text-muted-foreground">
        ¿Buscas montos y tendencias?{" "}
        <Link href="/bi" className="font-medium text-brand underline-offset-4 hover:underline">
          Abre el tablero de negocio
        </Link>
        {" · "}
        <Link href="/informe" className="font-medium text-brand underline-offset-4 hover:underline">
          Ver el informe
        </Link>
        .
      </p>
    </div>
  );
}
