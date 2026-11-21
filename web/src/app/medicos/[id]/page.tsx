import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { AtencionList } from "@/components/atencion-list";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { EmptyState } from "@/components/empty-state";
import { EntityRow } from "@/components/entity-row";
import { KpiCard } from "@/components/kpi-card";
import { PageHeader } from "@/components/page-header";
import { SectionCard } from "@/components/section-card";
import { formatDate } from "@/lib/format";
import { MEDICO_ATENCION_LIMIT, getMedicoDetail, getMedicoPageTitle } from "@/lib/medico-data";

export const dynamic = "force-dynamic";

const n = (v: number) => v.toLocaleString("es-VE");

const SOURCE_LABELS: Record<string, string> = {
  ocr_label: "Etiqueta",
  ocr_title: "Sello",
  review: "Revisión",
};

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const title = await getMedicoPageTitle(id);
  return { title: title ? `${title} · Médicos · Ávila GPS` : "Médico · Ávila GPS" };
}

export default async function MedicoDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const detail = await getMedicoDetail(id);
  if (!detail) notFound();
  if (detail.medico.merged_into) redirect(`/medicos/${detail.medico.merged_into}`);

  const { medico, especialidades, stats, patients, atenciones, mentions, openReviews } = detail;
  const name = `${medico.title === "dra" ? "Dra." : "Dr."} ${medico.full_name}`;
  const primary = especialidades.find((e) => e.is_primary);
  const facts: [string, string][] = [
    ["MPPS", medico.mpps || "Sin MPPS leído"],
    ["Colegio", medico.colegio_number || "—"],
    ["RIF", medico.rif || "—"],
    ["Título", [medico.degree, medico.degree_university].filter(Boolean).join(" · ") || "—"],
    ["Primera atención", stats.firstSeen ? formatDate(stats.firstSeen) : "—"],
    ["Última atención", stats.lastSeen ? formatDate(stats.lastSeen) : "—"],
  ];

  return (
    <div className="space-y-6">
      <Breadcrumbs
        items={[
          { href: "/", label: "Inicio" },
          { href: "/medicos", label: "Médicos" },
          { label: name },
        ]}
      />
      <PageHeader
        eyebrow={primary ? `${primary.area_name} · ${primary.name_es}` : "Médico"}
        title={name}
        description={`Reconocido en ${n(mentions)} ${mentions === 1 ? "mención" : "menciones"} de documentos.`}
        badges={[
          medico.mpps
            ? { label: `MPPS ${medico.mpps}` }
            : { label: "Sin MPPS · por nombre", className: "rounded-full bg-warning-soft px-3 py-1 text-xs font-medium text-warning" },
          ...(openReviews > 0
            ? [{ label: `${n(openReviews)} en revisión`, className: "rounded-full bg-warning-soft px-3 py-1 text-xs font-medium text-warning" }]
            : []),
        ]}
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <KpiCard featured label="Atenciones" value={n(stats.atenciones)} />
        <KpiCard label="Pacientes" value={n(stats.pacientes)} />
        <KpiCard label="Facturas" value={n(stats.facturas)} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard title="Ficha" description="Datos leídos del sello y del membrete.">
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            {facts.map(([label, value]) => (
              <div key={label}>
                <dt className="text-xs tracking-wider text-muted-foreground uppercase">{label}</dt>
                <dd className="break-words">{value}</dd>
              </div>
            ))}
          </dl>
        </SectionCard>
        <SectionCard title="Especialidades" description="La principal tiene más evidencia; una subespecialidad gana a su especialidad madre.">
          {especialidades.length === 0 ? (
            <p className="text-sm text-muted-foreground">Ningún sello de este médico nombra una especialidad.</p>
          ) : (
            <ul className="space-y-2">
              {especialidades.map((e) => (
                <li
                  key={e.code}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-border bg-muted/60 px-4 py-2.5 text-sm"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-foreground">{e.name_es}</span>
                    {e.is_primary ? (
                      <span className="rounded-full bg-hero px-2 py-0.5 text-[11px] font-medium text-white">Principal</span>
                    ) : null}
                    <span className="text-xs text-muted-foreground">
                      {e.parent_name ? `${e.parent_name} · ` : ""}
                      {e.area_name}
                    </span>
                  </div>
                  <span className="text-xs tabular-nums text-muted-foreground">
                    {SOURCE_LABELS[e.source] || e.source} · {n(e.evidence_count)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>

      <SectionCard title="Pacientes" description="Personas con al menos una atención de este médico.">
        {patients.length === 0 ? (
          <EmptyState title="Sin pacientes vinculados" hint="Las atenciones de este médico aún no tienen persona resuelta." />
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            {patients.map((p) => (
              <EntityRow
                key={`${p.person_id}-${p.especialidad || ""}`}
                href={`/personas/${p.person_id}`}
                title={p.full_name || p.identity_number || "Sin nombre"}
                meta={[p.especialidad, p.last_seen ? `Última ${formatDate(p.last_seen)}` : null].filter(Boolean).join(" · ")}
                trailing={`${n(p.atenciones)}`}
              />
            ))}
          </div>
        )}
      </SectionCard>

      <SectionCard
        title="Atenciones"
        description={
          stats.atenciones > atenciones.length
            ? `Las ${MEDICO_ATENCION_LIMIT} más recientes de ${n(stats.atenciones)}.`
            : "Informes, órdenes y resultados firmados por este médico."
        }
      >
        <AtencionList
          rows={atenciones}
          hide="medico"
          emptyTitle="Sin atenciones"
          emptyHint="Este médico solo aparece mencionado, sin informe propio."
        />
      </SectionCard>
    </div>
  );
}
