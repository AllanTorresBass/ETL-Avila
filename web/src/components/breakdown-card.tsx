import Link from "next/link";
import { SectionCard } from "@/components/section-card";

export type BreakdownRow = {
  key: string;
  label: string;
  /** Value that drives the bar length. */
  value: number;
  /** Text shown on the right. */
  display: string;
  hint?: string;
  href?: string;
};

export function BreakdownList({ rows, empty }: { rows: BreakdownRow[]; empty: string }) {
  const max = Math.max(1, ...rows.map((r) => r.value));

  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">{empty}</p>;
  }

  return (
    <ul className="-mx-2 space-y-0.5">
      {rows.map((row) => {
        const inner = (
          <>
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="min-w-0 truncate font-medium text-foreground">{row.label}</span>
              <span className="shrink-0 tabular-nums text-foreground">
                {row.display}
                {row.hint ? <span className="ml-2 text-xs text-muted-foreground">{row.hint}</span> : null}
              </span>
            </div>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-brand/80 transition-[width] duration-700"
                style={{ width: `${Math.max(2, Math.round((row.value / max) * 100))}%` }}
              />
            </div>
          </>
        );
        return (
          <li key={row.key}>
            {row.href ? (
              <Link href={row.href} className="block rounded-xl px-2 py-2 transition-colors hover:bg-muted">
                {inner}
              </Link>
            ) : (
              <div className="px-2 py-2">{inner}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function BreakdownCard({
  title,
  description,
  rows,
  empty,
  className,
}: {
  title: string;
  description?: string;
  rows: BreakdownRow[];
  empty: string;
  className?: string;
}) {
  return (
    <SectionCard title={title} description={description} className={className}>
      <BreakdownList rows={rows} empty={empty} />
    </SectionCard>
  );
}
