import Link from "next/link";
import { ArrowRight, CircleCheck } from "lucide-react";

export type AttentionItem = {
  id: string;
  title: string;
  hint: string;
  count: number;
  href: string;
  tone: "danger" | "warning" | "info";
};

const TONE: Record<AttentionItem["tone"], string> = {
  danger: "bg-danger-soft text-danger",
  warning: "bg-warning-soft text-warning",
  info: "bg-brand/10 text-brand",
};

export function AttentionPanel({ items }: { items: AttentionItem[] }) {
  const open = items.filter((i) => i.count > 0);

  return (
    <section
      aria-labelledby="atencion-titulo"
      className="rounded-3xl border border-border bg-card p-5 shadow-sm sm:p-6"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="atencion-titulo" className="text-lg font-semibold text-foreground">
          Requiere atención
        </h2>
        <p className="text-sm text-muted-foreground">
          {open.length > 0
            ? `${open.length} ${open.length === 1 ? "tema pendiente" : "temas pendientes"}`
            : "Sin pendientes"}
        </p>
      </div>

      {open.length === 0 ? (
        <div className="mt-4 flex items-center gap-3 rounded-2xl bg-success-soft p-4 text-success">
          <CircleCheck aria-hidden="true" className="size-5 shrink-0" />
          <p className="text-sm font-medium">
            Todo en orden: no hay casos abiertos ni cargas fallidas.
          </p>
        </div>
      ) : (
        <ul className="mt-4 divide-y divide-border">
          {open.map((item) => (
            <li key={item.id}>
              <Link
                href={item.href}
                className="group -mx-2 flex items-center gap-4 rounded-2xl px-2 py-3 transition-colors hover:bg-muted"
              >
                <span
                  className={`inline-flex min-w-14 justify-center rounded-full px-3 py-1 text-sm font-semibold tabular-nums ${TONE[item.tone]}`}
                >
                  {item.count.toLocaleString("es-VE")}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-foreground">{item.title}</span>
                  <span className="block text-sm text-muted-foreground">{item.hint}</span>
                </span>
                <ArrowRight
                  aria-hidden="true"
                  className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-brand"
                />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
