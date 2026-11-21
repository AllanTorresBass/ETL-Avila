import { Skeleton } from "@/components/ui/skeleton";

export default function EspecialidadesLoading() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Cargando especialidades">
      <div className="space-y-2">
        <Skeleton className="h-4 w-24 rounded-lg" />
        <Skeleton className="h-9 w-56 rounded-xl" />
        <Skeleton className="h-4 w-full max-w-xl rounded-lg" />
      </div>
      <div className="rounded-3xl border border-border bg-card p-5 sm:p-6">
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
    </div>
  );
}
