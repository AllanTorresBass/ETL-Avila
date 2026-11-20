import { Suspense } from "react";
import { FacturaListKpisConnected } from "@/components/factura-list-kpis-connected";
import { getFacturaListKpis } from "@/lib/factura-data";

/** Server fetch for corpus KPIs; active filter state is read on the client. */
export async function FacturaListKpisLoader() {
  const kpis = await getFacturaListKpis();
  return (
    <Suspense fallback={null}>
      <FacturaListKpisConnected kpis={kpis} />
    </Suspense>
  );
}
