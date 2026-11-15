export function ResultCount({ shown, total }: { shown: number; total: number }) {
  return (
    <p className="text-xs text-slate-500">
      Mostrando {shown.toLocaleString("es-VE")} de {total.toLocaleString("es-VE")}
    </p>
  );
}
