import Link from "next/link";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

type KpiCardProps = {
  label: string;
  value: string;
  hint?: string;
  /** Relative change vs the previous period (0.12 = +12%). Null hides the chip. */
  delta?: number | null;
  deltaLabel?: string;
  icon?: React.ReactNode;
  href?: string;
  featured?: boolean;
};

function DeltaChip({ delta, label }: { delta: number; label?: string }) {
  const flat = Math.abs(delta) < 0.005;
  const up = delta > 0;
  const Icon = flat ? Minus : up ? ArrowUpRight : ArrowDownRight;
  const tone = flat ? "bg-muted text-muted-foreground" : up ? "bg-success-soft text-success" : "bg-danger-soft text-danger";
  const text = `${up ? "+" : ""}${(delta * 100).toFixed(Math.abs(delta) < 0.1 ? 1 : 0)}%`;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums ${tone}`}>
      <Icon aria-hidden="true" className="size-3" />
      {text}
      <span className="sr-only">{label ?? "frente al periodo anterior"}</span>
    </span>
  );
}

export function KpiCard({ label, value, hint, delta, deltaLabel, icon, href, featured }: KpiCardProps) {
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className={`text-sm font-medium ${featured ? "text-hero-foreground/80" : "text-muted-foreground"}`}>
          {label}
        </span>
        {icon ? (
          <span
            aria-hidden="true"
            className={`flex size-8 items-center justify-center rounded-full ${featured ? "bg-white/10" : "bg-brand/10 text-brand"}`}
          >
            {icon}
          </span>
        ) : null}
      </div>
      <p className="mt-3 text-3xl font-semibold tracking-tight tabular-nums">{value}</p>
      <div className="mt-2 flex min-h-6 flex-wrap items-center gap-2">
        {delta != null ? <DeltaChip delta={delta} label={deltaLabel} /> : null}
        {hint ? (
          <span className={`text-xs ${featured ? "text-hero-foreground/70" : "text-muted-foreground"}`}>{hint}</span>
        ) : null}
      </div>
    </>
  );

  const base = `group block rounded-3xl border p-5 shadow-sm transition-[border-color,box-shadow] ${
    featured
      ? "border-transparent bg-hero text-hero-foreground"
      : "border-border bg-card text-foreground hover:border-brand/40 hover:shadow-md"
  }`;

  if (!href) return <div className={base}>{body}</div>;
  return (
    <Link href={href} className={base}>
      {body}
    </Link>
  );
}
