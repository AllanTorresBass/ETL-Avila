import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { EmptyState } from "@/components/empty-state";
import { EntityTabs, type EntityTabPanel } from "@/components/entity-tabs";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { can } from "@/lib/access";
import { requirePermission } from "@/lib/auth";
import { firstParam } from "@/lib/list-params";
import {
  getEspecialidadBacklog,
  getEspecialidadTree,
  type EspecialidadBacklogRow,
  type EspecialidadTreeRow,
} from "@/lib/medico-data";

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

const BACKLOG_TAB = "sin-catalogo";

type AreaGroup = {
  code: string;
  name: string;
  roots: { row: EspecialidadTreeRow; children: EspecialidadTreeRow[] }[];
};

type Backlog = {
  rows: EspecialidadBacklogRow[];
  observations: number;
  unknown: number;
  openReviews: number;
};

function countLabel(count: number, one: string, many: string): string {
  return `${n(count)} ${count === 1 ? one : many}`;
}

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

function areaDescription(area: AreaGroup): string {
  const subs = area.roots.reduce((sum, node) => sum + node.children.length, 0);
  const atenciones = area.roots.reduce((sum, node) => sum + node.row.atenciones, 0);
  const procedimientos = area.roots.reduce((sum, node) => sum + node.row.procedimientos, 0);
  const parts = [countLabel(area.roots.length, "especialidad", "especialidades")];
  if (subs > 0) parts.push(countLabel(subs, "subespecialidad", "subespecialidades"));
  parts.push(countLabel(atenciones, "atención", "atenciones"));
  if (procedimientos > 0) parts.push(countLabel(procedimientos, "procedimiento", "procedimientos"));
  return parts.join(" · ");
}

function SpecialtyGrid({ area }: { area: AreaGroup }) {
  return (
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
  );
}

function BacklogBody({ backlog }: { backlog: Backlog }) {
  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Link
          href="/revision?tipo=medico"
          className="rounded-full border border-border px-4 py-2 text-sm font-medium text-brand"
        >
          Ver revisión
        </Link>
      </div>
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
    </div>
  );
}

function TabsFallback() {
  return (
    <div className="rounded-3xl border border-border bg-card p-5 shadow-sm sm:p-6" aria-hidden="true">
      <div className="flex flex-wrap gap-2">
        {Array.from({ length: 7 }, (_, i) => (
          <Skeleton key={i} className="h-9 w-36 rounded-full" />
        ))}
      </div>
      <Skeleton className="mt-5 h-6 w-48 rounded-lg" />
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-28 rounded-2xl" />
        ))}
      </div>
    </div>
  );
}

export default async function EspecialidadesPage({
  searchParams,
}: {
  searchParams: Promise<{ area?: string | string[] }>;
}) {
  const sp = await searchParams;
  const user = await requirePermission("read");
  const canReview = can(user.role, "review");
  const [tree, backlog] = await Promise.all([
    getEspecialidadTree(),
    canReview ? getEspecialidadBacklog() : Promise.resolve(null),
  ]);
  const areas = groupTree(tree);
  const panels: EntityTabPanel[] = areas.map((area) => ({
    id: area.code,
    label: area.name,
    count: n(area.roots.length),
    title: area.name,
    description: areaDescription(area),
    body: <SpecialtyGrid area={area} />,
  }));
  if (backlog) {
    panels.push({
      id: BACKLOG_TAB,
      label: "Sin catálogo",
      count: n(backlog.unknown),
      title: "Términos sin especialidad",
      description: `${n(backlog.unknown)} de ${n(backlog.observations)} términos leídos no coinciden con el catálogo · ${n(backlog.openReviews)} casos abiertos.`,
      body: <BacklogBody backlog={backlog} />,
    });
  }
  const requested = firstParam(sp.area);
  const defaultArea = panels.some((panel) => panel.id === requested) ? requested : (panels[0]?.id ?? "clinica");

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Taxonomía"
        title="Especialidades"
        description="Área, especialidad y subespecialidad. Los conteos de una especialidad incluyen sus subespecialidades."
        badges={[{ label: `${n(tree.length)} especialidades` }]}
      />

      {panels.length === 0 ? (
        <EmptyState
          title="Aún no hay especialidades"
          hint="Ejecuta especialidad_catalog.py load --apply para cargar el catálogo."
        />
      ) : (
        <Suspense fallback={<TabsFallback />}>
          <EntityTabs
            panels={panels}
            defaultValue={defaultArea}
            paramName="area"
            ariaLabel="Áreas de especialidad"
          />
        </Suspense>
      )}
    </div>
  );
}
