import { FacturasFilterSkeleton, FacturasListSkeleton } from "@/components/facturas-page-skeleton";

/** Soft-nav within the list: keep header/KPIs, skeleton filters + rows. */
export default function FacturasBrowseLoading() {
  return (
    <div className="space-y-6">
      <FacturasFilterSkeleton />
      <FacturasListSkeleton />
    </div>
  );
}
