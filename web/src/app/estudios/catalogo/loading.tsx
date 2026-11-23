import { Skeleton } from "@/components/ui/skeleton";

export default function EstudioCatalogoLoading() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Cargando catálogo">
      <div className="space-y-2">
        <Skeleton className="h-4 w-24 rounded-lg" />
        <Skeleton className="h-9 w-48 rounded-xl" />
        <Skeleton className="h-4 w-full max-w-xl rounded-lg" />
      </div>
      <div className="rounded-3xl border border-border bg-card p-5 sm:p-6">
        <div className="flex flex-wrap gap-2">
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton key={index} className="h-9 w-32 rounded-full" />
          ))}
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          {Array.from({ length: 4 }, (_, index) => (
            <Skeleton key={index} className="h-40 rounded-2xl" />
          ))}
        </div>
      </div>
    </div>
  );
}
