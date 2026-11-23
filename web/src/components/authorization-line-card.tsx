import Link from "next/link";
import type { ReactNode } from "react";
import { authItems, formatAuthDate, formatAuthHeading, formatAuthItem, formatMoney } from "@/lib/format";

export type AuthorizationLineView = {
  id: string;
  aps_code?: string | null;
  clave_rms?: string | null;
  service_date?: string | Date | null;
  request_date?: string | Date | null;
  period_month?: string | Date | null;
  diagnosis?: string | null;
  service_description?: string | null;
  contratante?: string | null;
  provider_name?: string | null;
  amount_bs?: string | number | null;
  amount_usd?: string | number | null;
  items?: unknown;
};

export function AuthorizationLineCard({
  line,
  extra,
  href,
  badge,
}: {
  line: AuthorizationLineView;
  extra?: ReactNode;
  /** Detail page; the heading becomes a link. */
  href?: string;
  /** Shown next to the heading (for example the match status). */
  badge?: ReactNode;
}) {
  const items = authItems(line.items);
  const detail = line.diagnosis?.trim() || "";
  const heading = formatAuthHeading(line);
  return (
    <div className="rounded-2xl border border-border bg-muted/60 px-4 py-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex flex-wrap items-center gap-2">
          {href ? (
            <Link href={href} className="font-medium text-brand hover:underline">
              {heading}
            </Link>
          ) : (
            <span className="font-medium">{heading}</span>
          )}
          {badge}
        </span>
        <span className="text-muted-foreground">{formatAuthDate(line)}</span>
      </div>
      {detail ? <div className="mt-1 text-muted-foreground">{detail}</div> : null}
      {items.length > 0 ? (
        <ul className="mt-1 space-y-0.5 text-muted-foreground">
          {items.map((item, index) => (
            <li key={`${line.id}-${index}`}>{formatAuthItem(item)}</li>
          ))}
        </ul>
      ) : (
        <div className="mt-1 text-muted-foreground">{line.service_description || "Sin diagnóstico"}</div>
      )}
      {line.aps_code?.trim() && line.clave_rms?.trim() ? (
        <div className="mt-1 text-xs text-muted-foreground">{line.clave_rms}</div>
      ) : null}
      <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
        <span>{line.contratante || line.provider_name || "—"}</span>
        <span>BS {formatMoney(line.amount_bs)}</span>
        <span>USD {formatMoney(line.amount_usd)}</span>
        {extra}
      </div>
    </div>
  );
}
