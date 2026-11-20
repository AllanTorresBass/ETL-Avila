import { Skeleton } from "@/components/ui/skeleton";

/** Full-page skeleton for first load / hard navigation to /personas. */
export function PersonasPageSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Cargando personas">
      <div className="space-y-2">
        <Skeleton className="h-8 w-40 rounded-xl" />
        <Skeleton className="h-4 w-96 max-w-full rounded-lg" />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-32 rounded-3xl" />
        ))}
      </div>

      <Skeleton className="h-28 rounded-3xl" />

      <PersonasListSkeleton />
    </div>
  );
}

/** List-only skeleton while filters refresh. */
export function PersonasListSkeleton() {
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
              <Skeleton className="h-4 w-48 max-w-[70%] rounded-lg" />
              <Skeleton className="h-3 w-64 max-w-full rounded-lg" />
              <div className="flex gap-2">
                <Skeleton className="h-5 w-20 rounded-full" />
                <Skeleton className="h-5 w-24 rounded-full" />
              </div>
            </div>
            <Skeleton className="h-3 w-12 rounded-lg" />
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
