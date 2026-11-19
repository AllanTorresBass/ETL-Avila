import { TriangleAlert } from "lucide-react";

export function DashboardNotice({ failures }: { failures: string[] }) {
  if (failures.length === 0) return null;
  return (
    <div
      role="status"
      className="flex items-start gap-3 rounded-2xl border border-warning/30 bg-warning-soft px-4 py-3 text-sm text-warning"
    >
      <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
      <p>
        No se pudieron cargar algunos datos ({failures.join(", ")}). Esos bloques aparecen vacíos; recarga la página
        para reintentar.
      </p>
    </div>
  );
}
