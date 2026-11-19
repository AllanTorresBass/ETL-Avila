import Link from "next/link";

type MeterProps = {
  label: string;
  value: number;
  total: number;
  href?: string;
  /** Explains what the ratio means, announced to screen readers. */
  description?: string;
};

export function Meter({ label, value, total, href, description }: MeterProps) {
  const ratio = total > 0 ? Math.min(1, value / total) : 0;
  const percent = Math.round(ratio * 100);
  const tone = ratio >= 0.9 ? "bg-success" : ratio >= 0.6 ? "bg-brand" : "bg-warning";

  const content = (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium text-foreground">{label}</span>
        <span className="text-sm text-muted-foreground tabular-nums">
          <span className="font-semibold text-foreground">{total > 0 ? `${percent}%` : "—"}</span>
          {" · "}
          {value.toLocaleString("es-VE")} / {total.toLocaleString("es-VE")}
        </span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-valuetext={`${percent}% (${value} de ${total})`}
        className="h-2 overflow-hidden rounded-full bg-muted"
      >
        <div
          className={`h-full rounded-full transition-[width] duration-700 ${tone}`}
          style={{ width: `${percent}%` }}
        />
      </div>
      {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
    </div>
  );

  if (!href) return content;
  return (
    <Link href={href} className="block rounded-xl transition-opacity hover:opacity-80">
      {content}
    </Link>
  );
}
