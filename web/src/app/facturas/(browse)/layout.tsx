import { Suspense } from "react";
import { FacturaListKpisLoader } from "@/components/factura-list-kpis-loader";
import { FacturasKpiSkeleton } from "@/components/facturas-kpi-skeleton";
import { PageHeader } from "@/components/page-header";

/**
 * List-only shell: KPIs stream once here and stay mounted across `?filter` navigations,
 * so clicking a KPI card does not flash the indicator skeleton again.
 */
export default function FacturasBrowseLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-6">
      <div className="facturas-no-print">
        <PageHeader title="Facturas" description="Directorio del universo inventariado." />
      </div>
      <div className="facturas-no-print">
        <Suspense fallback={<FacturasKpiSkeleton />}>
          <FacturaListKpisLoader />
        </Suspense>
      </div>
      {children}
    </div>
  );
}
