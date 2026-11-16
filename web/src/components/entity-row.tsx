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
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-slate-100 bg-white px-4 py-3 text-sm shadow-sm transition hover:border-[#5BB2F5]/40 hover:shadow-md">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`font-medium ${href ? "text-[#033CA0]" : "text-slate-800"}`}>
            {title}
          </span>
          {badges?.map((b) => (
            <Badge
              key={b}
              variant="secondary"
              className="rounded-full bg-[#033CA0]/10 text-[#033CA0]"
            >
              {b}
            </Badge>
          ))}
        </div>
        {meta ? <div className="text-xs text-slate-500">{meta}</div> : null}
      </div>
      {trailing ? <div className="text-xs text-slate-500">{trailing}</div> : null}
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
