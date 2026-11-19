import Link from "next/link";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";

export function EntityRow({
  href,
  title,
  meta,
  badges,
  trailing,
}: {
  href?: string;
  title: string;
  meta?: string;
  badges?: string[];
  trailing?: ReactNode;
}) {
  const body = (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-border bg-card px-4 py-3 text-sm shadow-sm transition hover:border-brand/40 hover:shadow-md">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`font-medium ${href ? "text-brand" : "text-foreground"}`}>
            {title}
          </span>
          {badges?.map((b) => (
            <Badge
              key={b}
              variant="secondary"
              className="rounded-full bg-brand/10 text-brand"
            >
              {b}
            </Badge>
          ))}
        </div>
        {meta ? <div className="text-xs text-muted-foreground">{meta}</div> : null}
      </div>
      {trailing ? <div className="text-xs text-muted-foreground">{trailing}</div> : null}
    </div>
  );

  if (href) {
    return (
      <Link href={href} className="block">
        {body}
      </Link>
    );
  }
  return body;
}
