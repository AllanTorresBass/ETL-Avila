import { Skeleton } from "@/components/ui/skeleton";

/** Card grid placeholder for the médicos directory and the especialidades tree. */
export function MedicosListSkeleton({ label = "Cargando médicos" }: { label?: string }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true" aria-label={label}>
      {Array.from({ length: 9 }, (_, i) => (
        <Skeleton key={i} className="h-36 rounded-3xl" />
      ))}
    </div>
  );
}

export function MedicosPageSkeleton({ label = "Cargando médicos" }: { label?: string }) {
  return (
    <div className="space-y-6" aria-busy="true" aria-label={label}>
      <div className="space-y-2">
        <Skeleton className="h-8 w-40 rounded-xl" />
        <Skeleton className="h-4 w-96 max-w-full rounded-lg" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-32 rounded-3xl" />
        ))}
      </div>
      <Skeleton className="h-11 w-full rounded-xl" />
      <MedicosListSkeleton label={label} />
    </div>
  );
}
