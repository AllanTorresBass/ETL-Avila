import Link from "next/link";

export type StatusSegment = { key: string; label: string; value: number; tone: string; href?: string };

/** One horizontal bar split by status, with a labelled legend underneath. */
export function StatusStack({ segments, empty }: { segments: StatusSegment[]; empty: string }) {
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  if (total === 0) return <p className="text-sm text-muted-foreground">{empty}</p>;

  return (
    <div className="space-y-4">
      <div
        role="img"
        aria-label={segments.map((s) => `${s.label}: ${s.value}`).join(", ")}
        className="flex h-3 overflow-hidden rounded-full bg-muted"
      >
        {segments
          .filter((s) => s.value > 0)
          .map((s) => (
            <div key={s.key} className={s.tone} style={{ width: `${(s.value / total) * 100}%` }} />
          ))}
      </div>
      <ul className="grid grid-cols-2 gap-x-4 gap-y-2">
        {segments.map((s) => {
          const row = (
            <>
              <span aria-hidden="true" className={`size-2.5 shrink-0 rounded-full ${s.tone}`} />
              <span className="min-w-0 flex-1 truncate text-sm text-foreground">{s.label}</span>
              <span className="text-sm tabular-nums text-muted-foreground">{s.value.toLocaleString("es-VE")}</span>
            </>
          );
          return (
            <li key={s.key}>
              {s.href && s.value > 0 ? (
                <Link href={s.href} className="flex items-center gap-2 rounded-lg py-0.5 transition-opacity hover:opacity-70">
                  {row}
                </Link>
              ) : (
                <div className="flex items-center gap-2 py-0.5">{row}</div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
