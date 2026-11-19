import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

type StatCardProps = {
  label: string;
  value: string | number;
  hint?: string;
  href?: string;
};

export function StatCard({ label, value, hint, href }: StatCardProps) {
  const body = (
    <>
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-medium text-muted-foreground">{label}</span>
        {href ? (
          <ArrowUpRight
            aria-hidden="true"
            className="size-4 shrink-0 text-muted-foreground transition-colors group-hover:text-brand"
          />
        ) : null}
      </div>
      <div className="mt-3 text-3xl font-semibold tracking-tight text-foreground tabular-nums">
        {typeof value === "number" ? value.toLocaleString("es-VE") : value}
      </div>
      {hint ? <p className="mt-1 text-sm text-muted-foreground">{hint}</p> : null}
    </>
  );

  const base = "group block rounded-2xl border border-border bg-card p-5 shadow-sm";
  if (!href) return <div className={base}>{body}</div>;
  return (
    <Link
      href={href}
      className={`${base} transition-[border-color,box-shadow] hover:border-brand/40 hover:shadow-md`}
    >
      {body}
    </Link>
  );
}
