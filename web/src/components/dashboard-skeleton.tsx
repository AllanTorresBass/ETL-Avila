import { Skeleton } from "@/components/ui/skeleton";

export function DashboardSkeleton() {
  return (
    <div className="space-y-8" role="status" aria-label="Cargando tablero">
      <div className="space-y-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:justify-between">
          <Skeleton className="h-12 w-72 rounded-full" />
          <Skeleton className="h-11 w-full rounded-full lg:max-w-sm" />
        </div>
        <Skeleton className="h-4 w-24 rounded-full" />
        <Skeleton className="h-10 w-80 max-w-full rounded-xl" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-32 rounded-3xl" />
        ))}
      </div>
      <Skeleton className="h-72 rounded-3xl" />
      <div className="grid gap-6 lg:grid-cols-2">
        <Skeleton className="h-64 rounded-3xl" />
        <Skeleton className="h-64 rounded-3xl" />
      </div>
    </div>
  );
}
