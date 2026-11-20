import { pageRange } from "@/components/pagination";

export function ResultCount({
  shown,
  total,
  page,
  pageSize,
}: {
  shown: number;
  total: number;
  page?: number;
  pageSize?: number;
}) {
  if (total <= 0) {
    return <p className="text-xs text-muted-foreground">Sin resultados</p>;
  }

  if (page != null && pageSize != null) {
    const { from, to } = pageRange(page, pageSize, shown, total);
    return (
      <p className="text-xs text-muted-foreground">
        Mostrando{" "}
        <span className="font-medium tabular-nums text-foreground">
          {from.toLocaleString("es-VE")}–{to.toLocaleString("es-VE")}
        </span>{" "}
        de{" "}
        <span className="font-medium tabular-nums text-foreground">
          {total.toLocaleString("es-VE")}
        </span>
      </p>
    );
  }

  return (
    <p className="text-xs text-muted-foreground">
      Mostrando {shown.toLocaleString("es-VE")} de {total.toLocaleString("es-VE")}
    </p>
  );
}
