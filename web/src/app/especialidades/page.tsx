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
  listEspecialidadSpecialists,
  type EspecialidadBacklogRow,
  type EspecialidadSpecialist,
  type EspecialidadTreeRow,
} from "@/lib/medico-data";

export const metadata: Metadata = {
  title: "Especialidades · Ávila GPS",
  description: "Catálogo de especialidades con los médicos asignados a cada una.",
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

const UNASSIGNED_TAB = "sin-especialidad";
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

function specialistName(person: EspecialidadSpecialist): string {
  if (person.title === "dra") return `Dra. ${person.full_name}`;
  if (person.title === "dr") return `Dr. ${person.full_name}`;
  return person.full_name;
}

function SpecialistLine({ person }: { person: EspecialidadSpecialist }) {
  return (
    <li className="flex items-baseline justify-between gap-3 text-sm">
      <Link href={`/medicos/${person.id}`} className="hover:text-brand hover:underline">
        {specialistName(person)}
      </Link>
      <span className="shrink-0 tabular-nums text-muted-foreground" title={`${n(person.atenciones)} atenciones`}>
        {n(person.atenciones)}
      </span>
    </li>
  );
}

function SpecialtyGrid({
  area,
  byCode,
}: {
  area: AreaGroup;
  byCode: Map<string, EspecialidadSpecialist[]>;
}) {
  return (
    <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {area.roots.map(({ row, children }) => {
        const direct = byCode.get(row.code) ?? [];
        const withDoctors = children.filter((child) => (byCode.get(child.code) ?? []).length > 0);
        const empty = children.filter((child) => (byCode.get(child.code) ?? []).length === 0);
        return (
          <li key={row.code} className="rounded-2xl border border-border bg-muted/60 p-4">
            <Link href={`/medicos?especialidad=${row.code}`} className="font-medium text-brand hover:underline">
              {row.name_es}
            </Link>
            <p className="mt-1 text-xs tabular-nums text-muted-foreground">
              {countLabel(row.medicos, "médico", "médicos")} · {countLabel(row.atenciones, "atención", "atenciones")}
              {row.procedimientos > 0 ? ` · ${countLabel(row.procedimientos, "procedimiento", "procedimientos")}` : ""}
            </p>
            {direct.length > 0 ? (
              <ul className="mt-3 space-y-1.5 border-t border-border pt-3">
                {direct.map((person) => (
                  <SpecialistLine key={person.id} person={person} />
                ))}
              </ul>
            ) : null}
            {withDoctors.length > 0 ? (
              <div className="mt-3 space-y-3 border-t border-border pt-3">
                {withDoctors.map((child) => (
                  <div key={child.code}>
                    <Link
                      href={`/medicos?especialidad=${child.code}`}
                      className="text-xs font-medium text-brand hover:underline"
                    >
                      {child.name_es}
                    </Link>
                    <ul className="mt-1.5 space-y-1.5">
                      {(byCode.get(child.code) ?? []).map((person) => (
                        <SpecialistLine key={person.id} person={person} />
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            ) : null}
            {empty.length > 0 ? (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {empty.map((child) => (
                  <Link
                    key={child.code}
                    href={`/medicos?especialidad=${child.code}`}
                    className="rounded-full bg-brand/10 px-2.5 py-0.5 text-[11px] font-medium text-brand hover:bg-brand/15"
                  >
                    {child.name_es}
                  </Link>
                ))}
              </div>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function UnassignedBody({ people }: { people: EspecialidadSpecialist[] }) {
  return (
    <ul className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2 lg:grid-cols-3">
      {people.map((person) => (
        <SpecialistLine key={person.id} person={person} />
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
  const [tree, specialists, backlog] = await Promise.all([
    getEspecialidadTree(),
    listEspecialidadSpecialists(),
    canReview ? getEspecialidadBacklog() : Promise.resolve(null),
  ]);
  const byCode = new Map<string, EspecialidadSpecialist[]>();
  const unassigned: EspecialidadSpecialist[] = [];
  for (const person of specialists) {
    if (!person.code) {
      unassigned.push(person);
      continue;
    }
    const list = byCode.get(person.code) ?? [];
    list.push(person);
    byCode.set(person.code, list);
  }
  const doctorCount = new Set(specialists.map((person) => person.id)).size;
  const areas = groupTree(tree);
  const panels: EntityTabPanel[] = areas.map((area) => ({
    id: area.code,
    label: area.name,
    count: n(area.roots.length),
    title: area.name,
    description: areaDescription(area),
    body: <SpecialtyGrid area={area} byCode={byCode} />,
  }));
  if (unassigned.length > 0) {
    panels.push({
      id: UNASSIGNED_TAB,
      label: "Sin especialidad",
      count: n(unassigned.length),
      title: "Médicos sin especialidad",
      description: `${countLabel(unassigned.length, "médico", "médicos")} del directorio todavía no tienen una especialidad del catálogo.`,
      body: <UnassignedBody people={unassigned} />,
    });
  }
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
        eyebrow="Catálogo"
        title="Especialidades"
        description="Cada área agrupa sus especialidades, y cada especialidad lista los médicos que el catálogo le asignó. El conteo de una especialidad incluye sus subespecialidades."
        badges={[{ label: `${n(tree.length)} especialidades` }, { label: `${n(doctorCount)} médicos` }]}
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
