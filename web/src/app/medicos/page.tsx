import type { Metadata } from "next";
import { Suspense } from "react";
import { Stethoscope } from "lucide-react";
import { KpiCard } from "@/components/kpi-card";
import { ListFilterBar } from "@/components/list-filter-bar";
import { MedicosListSkeleton } from "@/components/medicos-page-skeleton";
import { MedicosResults, medicoFilterParams, type MedicosSearchInput } from "@/components/medicos-results";
import { PageHeader } from "@/components/page-header";
import { ScrollToAnchor } from "@/components/scroll-to-anchor";
import { buildListHref, firstParam, hasActiveFilters, omitParam, type ActiveChip } from "@/lib/list-params";
import { getMedicoKpis, listEspecialidadOptions } from "@/lib/medico-data";

export const metadata: Metadata = {
  title: "Médicos · Ávila GPS",
  description: "Directorio de médicos leído de informes, órdenes y resultados, con especialidad y pacientes.",
};

export const dynamic = "force-dynamic";

const n = (v: number) => v.toLocaleString("es-VE");

export default async function MedicosPage({ searchParams }: { searchParams: Promise<MedicosSearchInput> }) {
  const sp = await searchParams;
  const [kpis, options] = await Promise.all([getMedicoKpis(), listEspecialidadOptions()]);
  const params = medicoFilterParams(sp);
  const areas = [...new Map(options.map((o) => [o.area_code, o.area_name])).entries()];
  const especialidadName = new Map(options.map((o) => [o.code, o.name_es]));
  const areaName = new Map(areas);

  const chips: ActiveChip[] = [];
  const chip = (key: string, label: string) =>
    chips.push({ key, label, clearHref: `${buildListHref("/medicos", omitParam(params, key))}#lista` });
  if (params.q) chip("q", `Buscar: ${params.q}`);
  if (params.area) chip("area", areaName.get(params.area) || params.area);
  if (params.especialidad) chip("especialidad", especialidadName.get(params.especialidad) || params.especialidad);
  if (params.has_mpps) chip("has_mpps", params.has_mpps === "1" ? "Con MPPS" : "Sin MPPS");

  const listKey = JSON.stringify({ ...params, page: firstParam(sp.page) || "1" });

  return (
    <div className="space-y-6">
      <Suspense fallback={null}>
        <ScrollToAnchor id="lista" />
      </Suspense>
      <PageHeader
        eyebrow="Directorio"
        title="Médicos"
        description="Cada médico se reconoce por su MPPS o por su nombre en el sello del informe. La especialidad sale del sello, la etiqueta o el título."
      />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          featured
          label="Médicos en el directorio"
          value={n(kpis.medicos)}
          hint={`${n(kpis.conMpps)} con MPPS`}
          icon={<Stethoscope className="size-4" />}
        />
        <KpiCard
          label="Con especialidad"
          value={n(kpis.conEspecialidad)}
          href="/especialidades"
        />
        <KpiCard
          label="Atenciones leídas"
          value={n(kpis.atenciones)}
          hint={`${n(kpis.completas)} completas`}
        />
        <KpiCard label="Casos clínicos abiertos" value={n(kpis.openReviews)} href="/revision?tipo=medico" />
      </div>

      <ListFilterBar
        searchValue={firstParam(sp.q)}
        searchPlaceholder="Nombre o MPPS (mín. 2)"
        searchLabel="Buscar"
        clearHref={hasActiveFilters(params) ? "/medicos#lista" : undefined}
        hash="lista"
        activeChips={chips}
        selects={[
          {
            name: "area",
            label: "Área",
            value: params.area || "",
            emptyLabel: "Todas las áreas",
            options: areas.map(([code, name]) => ({ value: code, label: name })),
          },
          {
            name: "especialidad",
            label: "Especialidad",
            value: params.especialidad || "",
            emptyLabel: "Todas las especialidades",
            options: options
              .filter((o) => !params.area || o.area_code === params.area)
              .map((o) => ({ value: o.code, label: o.level === 2 ? `— ${o.name_es}` : o.name_es })),
          },
          {
            name: "has_mpps",
            label: "MPPS",
            value: params.has_mpps || "",
            emptyLabel: "Todos",
            options: [
              { value: "1", label: "Con MPPS" },
              { value: "0", label: "Sin MPPS" },
            ],
          },
        ]}
      />

      <Suspense key={listKey} fallback={<MedicosListSkeleton />}>
        <MedicosResults sp={sp} />
      </Suspense>
    </div>
  );
}
