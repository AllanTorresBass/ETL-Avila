import { Skeleton } from "@/components/ui/skeleton";

export function AutorizacionesListSkeleton({ label = "Cargando autorizaciones" }: { label?: string }) {
  return (
    <div className="grid gap-3 lg:grid-cols-2" aria-busy="true" aria-label={label}>
      {Array.from({ length: 8 }, (_, i) => (
        <Skeleton key={i} className="h-36 rounded-2xl" />
      ))}
    </div>
  );
}

export function AutorizacionesAnalyticsSkeleton({ label = "Cargando análisis" }: { label?: string }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2" aria-busy="true" aria-label={label}>
      {Array.from({ length: 6 }, (_, i) => (
        <Skeleton key={i} className="h-64 rounded-3xl" />
      ))}
    </div>
  );
}

export function AutorizacionesPageSkeleton({ label = "Cargando autorizaciones" }: { label?: string }) {
  return (
    <div className="space-y-6" aria-busy="true" aria-label={label}>
      <div className="space-y-2">
        <Skeleton className="h-8 w-48 rounded-xl" />
        <Skeleton className="h-4 w-96 max-w-full rounded-lg" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-32 rounded-3xl" />
        ))}
      </div>
      <Skeleton className="h-11 w-full rounded-xl" />
      <AutorizacionesListSkeleton label={label} />
    </div>
  );
}

export function AutorizacionDetailSkeleton({ label = "Cargando autorización" }: { label?: string }) {
  return (
    <div className="space-y-6" aria-busy="true" aria-label={label}>
      <div className="space-y-2">
        <Skeleton className="h-4 w-40 rounded-lg" />
        <Skeleton className="h-8 w-64 rounded-xl" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-28 rounded-3xl" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-56 rounded-3xl" />
        ))}
      </div>
    </div>
  );
}
