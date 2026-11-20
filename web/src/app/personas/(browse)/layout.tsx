import { Suspense } from "react";
import { PageHeader } from "@/components/page-header";
import { PersonaListKpisLoader } from "@/components/persona-list-kpis-loader";
import { PersonasKpiSkeleton } from "@/components/personas-kpi-skeleton";

/**
 * List-only shell: KPIs stream once here and stay mounted across `?filter` navigations,
 * so clicking a KPI card does not flash the indicator skeleton again.
 */
export default function PersonasBrowseLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Personas"
        description="Cliente = titular o beneficiario. Busca por cédula, nombre, teléfono o clave RMS."
      />
      <Suspense fallback={<PersonasKpiSkeleton />}>
        <PersonaListKpisLoader />
      </Suspense>
      {children}
    </div>
  );
}
