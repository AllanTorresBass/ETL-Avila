import { Skeleton } from "@/components/ui/skeleton";

export default function PersonaDetailLoading() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Cargando persona">
      <Skeleton className="h-4 w-56 rounded-lg" />
      <Skeleton className="h-56 rounded-3xl" />
      <Skeleton className="h-10 w-full rounded-full" />
      <Skeleton className="h-72 rounded-3xl" />
    </div>
  );
}
