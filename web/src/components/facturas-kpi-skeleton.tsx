import { Skeleton } from "@/components/ui/skeleton";

const KPI_SLOTS = 8;

/** Card-shaped KPI placeholders that match KpiCard anatomy while corpus metrics load. */
export function FacturasKpiSkeleton() {
  return (
    <section
      aria-busy="true"
      aria-label="Cargando indicadores"
      className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
    >
      {Array.from({ length: KPI_SLOTS }).map((_, i) => {
        const featured = i === 0;
        return (
          <div
            key={i}
            className={`rounded-3xl border p-5 shadow-sm ${
              featured ? "border-transparent bg-hero/90" : "border-border bg-card"
            }`}
            style={{ animationDelay: `${i * 35}ms` }}
          >
            <div className="flex items-center justify-between gap-2">
              <Skeleton
                className={`h-4 w-24 rounded-full ${featured ? "bg-white/25" : ""}`}
              />
              <Skeleton
                className={`size-8 rounded-full ${featured ? "bg-white/20" : ""}`}
              />
            </div>
            <Skeleton
              className={`mt-3 h-9 w-20 rounded-xl ${featured ? "bg-white/30" : ""}`}
            />
            <Skeleton
              className={`mt-3 h-3 w-32 max-w-full rounded-full ${featured ? "bg-white/20" : ""}`}
            />
          </div>
        );
      })}
    </section>
  );
}
