import Link from "next/link";
import { Activity, BarChart3, Search } from "lucide-react";
import { formatDateTime } from "@/lib/format-metrics";

export type DashboardId = "etl" | "bi";

const DASHBOARDS: { id: DashboardId; href: string; label: string; icon: typeof Activity }[] = [
  { id: "etl", href: "/etl", label: "ETL · Operación", icon: Activity },
  { id: "bi", href: "/bi", label: "BI · Negocio", icon: BarChart3 },
];

function DashboardSwitcher({ current }: { current: DashboardId }) {
  return (
    <nav
      aria-label="Tablero"
      className="inline-flex w-full gap-1 rounded-full border border-border bg-muted p-1 sm:w-auto"
    >
      {DASHBOARDS.map(({ id, href, label, icon: Icon }) => {
        const active = id === current;
        return (
          <Link
            key={id}
            href={href}
            aria-current={active ? "page" : undefined}
            className={`inline-flex min-h-10 flex-1 items-center justify-center gap-2 rounded-full px-4 text-sm font-medium whitespace-nowrap transition-colors sm:flex-none ${
              active
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Icon aria-hidden="true" className={`size-4 ${active ? "text-brand" : ""}`} />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

export function DashboardHeader({
  current,
  title,
  description,
  actions,
}: {
  current: DashboardId;
  title: string;
  description: string;
  actions?: React.ReactNode;
}) {
  return (
    <header className="space-y-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <DashboardSwitcher current={current} />
        <form action="/personas" method="get" role="search" className="relative w-full lg:max-w-sm">
          <label htmlFor="busqueda-global" className="sr-only">
            Buscar personas por nombre, cédula o RIF
          </label>
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-4 size-4 -translate-y-1/2 text-muted-foreground"
          />
          <input
            id="busqueda-global"
            name="q"
            type="search"
            placeholder="Buscar persona: nombre, cédula o RIF"
            autoComplete="off"
            className="h-11 w-full rounded-full border border-border bg-card pr-4 pl-11 text-sm text-foreground shadow-sm placeholder:text-muted-foreground"
          />
        </form>
      </div>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-medium tracking-[0.14em] text-brand uppercase">Ávila GPS</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-balance text-foreground sm:text-4xl">
            {title}
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-pretty text-muted-foreground sm:text-base">{description}</p>
        </div>
        <div className="flex flex-col items-start gap-2 sm:items-end">
          {actions}
          <p className="text-xs text-muted-foreground">Datos al {formatDateTime(new Date())}</p>
        </div>
      </div>
    </header>
  );
}
