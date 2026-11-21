import type { Metadata } from "next";
import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { SectionCard } from "@/components/section-card";
import { can } from "@/lib/access";
import { requirePermission } from "@/lib/auth";
import { getEspecialidadBacklog, getEspecialidadTree, type EspecialidadTreeRow } from "@/lib/medico-data";

export const metadata: Metadata = {
  title: "Especialidades · Ávila GPS",
  description: "Taxonomía de áreas, especialidades y subespecialidades con médicos y atenciones.",
};

export const dynamic = "force-dynamic";

const n = (v: number) => v.toLocaleString("es-VE");

const CONTEXT_LABELS: Record<string, string> = {
  label: "Etiqueta",
  doctor_title: "Sello",
  report_title: "Título",
  referral: "Referencia",
  fiscal_line: "Factura",
  workbook_servicio: "Sábana",
  auth_line: "Autorización",
  directory: "Directorio",
};

type AreaGroup = {
  code: string;
  name: string;
  roots: { row: EspecialidadTreeRow; children: EspecialidadTreeRow[] }[];
};

function groupTree(rows: EspecialidadTreeRow[]): AreaGroup[] {
  const areas = new Map<string, AreaGroup>();
  const roots = new Map<string, { row: EspecialidadTreeRow; children: EspecialidadTreeRow[] }>();
  for (const row of rows) {
    if (row.level !== 1) continue;
    const area = areas.get(row.area_code) ?? { code: row.area_code, name: row.area_name, roots: [] };
    areas.set(row.area_code, area);
    const node = { row, children: [] as EspecialidadTreeRow[] };
    roots.set(row.code, node);
    area.roots.push(node);
  }
  for (const row of rows) {
    if (row.level === 2 && row.parent_code) roots.get(row.parent_code)?.children.push(row);
  }
  return [...areas.values()];
}

export default async function EspecialidadesPage() {
  const user = await requirePermission("read");
  const canReview = can(user.role, "review");
  const [tree, backlog] = await Promise.all([
    getEspecialidadTree(),
    canReview ? getEspecialidadBacklog() : Promise.resolve(null),
  ]);
  const areas = groupTree(tree);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Taxonomía"
        title="Especialidades"
        description="Área, especialidad y subespecialidad. Los conteos de una especialidad incluyen sus subespecialidades."
        badges={[{ label: `${n(tree.length)} especialidades` }]}
      />

      {areas.length === 0 ? (
        <EmptyState
          title="Aún no hay especialidades"
          hint="Ejecuta especialidad_catalog.py load --apply para cargar el catálogo."
        />
      ) : (
        areas.map((area) => (
          <SectionCard key={area.code} title={area.name}>
            <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {area.roots.map(({ row, children }) => (
                <li key={row.code} className="rounded-2xl border border-border bg-muted/60 p-4">
                  <Link href={`/medicos?especialidad=${row.code}`} className="font-medium text-brand hover:underline">
                    {row.name_es}
                  </Link>
                  <p className="mt-1 text-xs tabular-nums text-muted-foreground">
                    {n(row.medicos)} médicos · {n(row.atenciones)} atenciones
                    {row.procedimientos > 0 ? ` · ${n(row.procedimientos)} procedimientos` : ""}
                  </p>
                  {children.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {children.map((child) => (
                        <Link
                          key={child.code}
                          href={`/medicos?especialidad=${child.code}`}
                          className="rounded-full bg-brand/10 px-2.5 py-0.5 text-[11px] font-medium text-brand hover:bg-brand/15"
                        >
                          {child.name_es} · {n(child.atenciones)}
                        </Link>
                      ))}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          </SectionCard>
        ))
      )}

      {backlog ? (
        <SectionCard
          title="Términos sin especialidad"
          description={`${n(backlog.unknown)} de ${n(backlog.observations)} términos leídos no coinciden con el catálogo · ${n(backlog.openReviews)} casos abiertos.`}
          action={
            <Link href="/revision?tipo=medico" className="rounded-full border border-border px-4 py-2 text-sm font-medium text-brand">
              Ver revisión
            </Link>
          }
        >
          {backlog.rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">Todos los términos leídos coinciden con el catálogo.</p>
          ) : (
            <ul className="flex flex-wrap gap-1.5">
              {backlog.rows.map((row) => (
                <li
                  key={`${row.context}-${row.l1_term}`}
                  className="rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground"
                >
                  <span className="font-medium text-foreground">{row.l1_term}</span> · {CONTEXT_LABELS[row.context] || row.context} ·{" "}
                  {n(row.occurrences)}
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      ) : null}
    </div>
  );
}
