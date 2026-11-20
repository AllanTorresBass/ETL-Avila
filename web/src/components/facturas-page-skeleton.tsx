import { Skeleton } from "@/components/ui/skeleton";
import { FacturasKpiSkeleton } from "@/components/facturas-kpi-skeleton";

/** Full-page skeleton for first load / hard navigation to /facturas. */
export function FacturasPageSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Cargando facturas">
      <div className="space-y-2">
        <Skeleton className="h-8 w-40 rounded-xl" />
        <Skeleton className="h-4 w-96 max-w-full rounded-lg" />
      </div>

      <FacturasKpiSkeleton />
      <FacturasFilterSkeleton />
      <FacturasListSkeleton />
    </div>
  );
}

/** Filter bar placeholder while accounts / chips resolve. */
export function FacturasFilterSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Cargando filtros">
      <div className="flex flex-wrap items-end gap-3">
        <Skeleton className="h-11 min-w-[12rem] flex-1 rounded-xl" />
        <Skeleton className="h-11 w-28 rounded-xl" />
        <Skeleton className="h-11 w-28 rounded-xl" />
        <Skeleton className="h-11 w-28 rounded-xl" />
        <Skeleton className="h-11 w-24 rounded-full" />
      </div>
      <div className="flex flex-wrap gap-2">
        <Skeleton className="h-7 w-24 rounded-full" />
        <Skeleton className="h-7 w-28 rounded-full" />
      </div>
    </div>
  );
}

/** List-only skeleton while filters refresh. */
export function FacturasListSkeleton() {
  return (
    <div id="lista" className="scroll-mt-24 space-y-3" aria-busy="true" aria-label="Cargando listado">
      <Skeleton className="h-4 w-48 rounded-lg" />
      <div className="overflow-hidden rounded-3xl border border-border bg-card shadow-sm">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="flex items-center justify-between gap-3 border-b border-border px-4 py-3.5 last:border-b-0 sm:px-5"
          >
            <div className="min-w-0 flex-1 space-y-2">
              <Skeleton className="h-4 w-40 max-w-[70%] rounded-lg" />
              <Skeleton className="h-3 w-64 max-w-full rounded-lg" />
            </div>
            <Skeleton className="h-3 w-16 rounded-lg" />
          </div>
        ))}
      </div>
      <div className="flex justify-between gap-3 pt-2">
        <Skeleton className="h-4 w-40 rounded-lg" />
        <div className="flex gap-1.5">
          <Skeleton className="size-9 rounded-full" />
          <Skeleton className="size-9 rounded-full" />
          <Skeleton className="size-9 rounded-full" />
        </div>
      </div>
    </div>
  );
}
